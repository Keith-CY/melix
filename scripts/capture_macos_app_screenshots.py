#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def run_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=capture_output,
        text=True,
        check=True,
    )


def default_output_dir() -> Path:
    tmp_root = Path("/private/tmp") if Path("/private/tmp").is_dir() else Path(tempfile.gettempdir())
    return Path(tempfile.mkdtemp(prefix="melix-app-screenshots-", dir=tmp_root))


def build_environment(repo_root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.setdefault("UV_CACHE_DIR", str(repo_root / ".uv-cache"))
    environment["UV_PROJECT_ENVIRONMENT"] = str(repo_root / ".venv")
    environment["HOME"] = str(repo_root / ".swift-home" / "app-screenshots")
    environment["CLANG_MODULE_CACHE_PATH"] = str(
        repo_root / ".build" / "ModuleCache.noindex" / "app-screenshots"
    )
    Path(environment["HOME"]).mkdir(parents=True, exist_ok=True)
    Path(environment["CLANG_MODULE_CACHE_PATH"]).mkdir(parents=True, exist_ok=True)
    return environment


def build_required_artifacts(repo_root: Path) -> None:
    environment = build_environment(repo_root)
    commands = [
        [
            "uv",
            "sync",
            "--project",
            "services/mlx-worker-python",
            "--extra",
            "mlx",
            "--frozen",
        ],
        [
            "xcrun",
            "swift",
            "build",
            "--product",
            "melix",
            "--disable-automatic-resolution",
        ],
        [
            "xcrun",
            "swift",
            "build",
            "--package-path",
            "services/mlx-text-worker-swift",
            "--product",
            "melix-text-worker-swift",
            "--disable-automatic-resolution",
        ],
        [
            "xcrun",
            "swift",
            "build",
            "--package-path",
            "apps/macos-menubar",
            "--product",
            "melix-menubar",
            "--disable-automatic-resolution",
        ],
    ]
    for command in commands:
        run_command(command, cwd=repo_root, env=environment)


def package_app(repo_root: Path, app_path: Path) -> dict[str, Any]:
    completed = run_command(
        [
            str(package_python_executable(repo_root)),
            "scripts/package_macos_menubar_app.py",
            "--repo-root",
            str(repo_root),
            "--output-path",
            str(app_path),
            "--json",
        ],
        cwd=repo_root,
        capture_output=True,
    )
    return json.loads(completed.stdout)


def package_python_executable(repo_root: Path) -> Path:
    repo_python = repo_root / ".venv" / "bin" / "python"
    if repo_python.is_file():
        return repo_python
    return Path(sys.executable)


def resolve_menubar_binary(app_path: Path) -> Path:
    candidate = app_path / "Contents" / "Resources" / "melix-menubar"
    if not candidate.is_file():
        raise FileNotFoundError(f"Missing bundled menubar binary: {candidate}")
    return candidate


def capture_screenshots(
    *,
    repo_root: Path,
    app_path: Path,
    output_dir: Path,
    width: int,
    height: int,
) -> dict[str, Any]:
    environment = os.environ.copy()
    environment.update(
        {
            "MELIX_APP_SCREENSHOT_CAPTURE": "1",
            "MELIX_APP_SCREENSHOT_OUTPUT_DIR": str(output_dir),
            "MELIX_APP_SCREENSHOT_APP_PATH": str(app_path),
            "MELIX_APP_SCREENSHOT_WIDTH": str(width),
            "MELIX_APP_SCREENSHOT_HEIGHT": str(height),
            "MELIX_HOME": str(output_dir / "melix-home"),
            "MELIX_REPO_ROOT": str(repo_root),
        }
    )
    completed = run_command(
        [str(resolve_menubar_binary(app_path))],
        cwd=repo_root,
        env=environment,
        capture_output=True,
    )
    payload = json.loads(completed.stdout)
    validate_capture_manifest(payload)
    return payload


def validate_capture_manifest(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != "melix.app_screenshots.v1":
        raise RuntimeError("Screenshot capture manifest has an unexpected schema_version.")
    screenshots = payload.get("screenshots")
    if not isinstance(screenshots, list) or not screenshots:
        raise RuntimeError("Screenshot capture manifest does not contain screenshots.")
    for screenshot in screenshots:
        path_value = screenshot.get("path") if isinstance(screenshot, dict) else None
        if not isinstance(path_value, str) or not path_value:
            raise RuntimeError("Screenshot capture manifest contains an entry without a path.")
        screenshot_path = Path(path_value)
        if not screenshot_path.is_file():
            raise RuntimeError(f"Screenshot file is missing: {screenshot_path}")
        if screenshot_path.read_bytes()[: len(PNG_SIGNATURE)] != PNG_SIGNATURE:
            raise RuntimeError(f"Screenshot file is not a PNG: {screenshot_path}")


def run_capture(
    *,
    repo_root: Path,
    output_dir: Path,
    skip_build: bool,
    width: int,
    height: int,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    app_path = output_dir / "Melix.app"
    if not skip_build:
        build_required_artifacts(repo_root)
    package_manifest = package_app(repo_root, app_path)
    packaged_app_path = Path(str(package_manifest.get("app_path", app_path))).expanduser().resolve()
    screenshot_manifest = capture_screenshots(
        repo_root=repo_root,
        app_path=packaged_app_path,
        output_dir=output_dir,
        width=width,
        height=height,
    )
    return {
        "ok": True,
        "output_dir": str(output_dir),
        "app_path": str(packaged_app_path),
        "package_manifest": package_manifest,
        "screenshot_manifest_path": screenshot_manifest["manifest_path"],
        "screenshot_root": screenshot_manifest["screenshot_root"],
        "screenshot_count": len(screenshot_manifest["screenshots"]),
        "screenshots": screenshot_manifest["screenshots"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build Melix.app and capture deterministic screenshots for every native app surface."
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=960)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable capture metadata.")
    args = parser.parse_args(argv)

    if args.width <= 0 or args.height <= 0:
        raise SystemExit("--width and --height must be positive integers.")

    repo_root = args.repo_root.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve() if args.output_dir else default_output_dir()
    try:
        payload = run_capture(
            repo_root=repo_root,
            output_dir=output_dir,
            skip_build=args.skip_build,
            width=args.width,
            height=args.height,
        )
    except subprocess.CalledProcessError as error:
        print(format_called_process_error(error), file=sys.stderr)
        return 1
    except (OSError, RuntimeError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Melix app screenshots: {payload['screenshot_root']}")
        print(f"Manifest: {payload['screenshot_manifest_path']}")
        print(f"Screenshots: {payload['screenshot_count']}")
    return 0


def format_called_process_error(error: subprocess.CalledProcessError) -> str:
    lines = [str(error)]
    if error.stdout:
        lines.append("stdout:")
        lines.append(error.stdout.rstrip())
    if error.stderr:
        lines.append("stderr:")
        lines.append(error.stderr.rstrip())
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
