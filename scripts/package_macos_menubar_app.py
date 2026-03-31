#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.productization.macos_app_bundle import (
    archive_macos_app_bundle,
    resolve_python_runtime_root,
    resolve_site_packages_root,
    write_unsigned_macos_app_bundle,
)


def resolve_built_binary(repo_root: Path) -> Path:
    build_root = repo_root / "apps/macos-menubar/.build"
    candidates = sorted(build_root.glob("*/debug/melix-menubar"))
    if build_root.joinpath("debug/melix-menubar").exists():
        candidates.insert(0, build_root / "debug/melix-menubar")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "Unable to find built `melix-menubar`. Run `swift test --package-path apps/macos-menubar` first."
    )


def resolve_built_swift_text_worker_binary(repo_root: Path) -> Path:
    build_root = repo_root / "services/mlx-text-worker-swift/.build"
    candidates = sorted(build_root.glob("*/debug/melix-text-worker-swift"))
    if build_root.joinpath("debug/melix-text-worker-swift").exists():
        candidates.insert(0, build_root / "debug/melix-text-worker-swift")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "Unable to find built `melix-text-worker-swift`. Run `swift test --package-path services/mlx-text-worker-swift` first."
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--output-path", default="/tmp/Melix.app")
    parser.add_argument("--home-dir", default=str(Path.home()))
    parser.add_argument("--app-name", default="Melix")
    parser.add_argument("--bundle-id", default="io.melix.menubar.preview")
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--archive-path", default="")
    parser.add_argument("--python-runtime-root", default="")
    parser.add_argument("--python-site-packages-path", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    menubar_binary = resolve_built_binary(repo_root)
    swift_worker_binary = resolve_built_swift_text_worker_binary(repo_root)
    python_runtime_root = (
        Path(args.python_runtime_root).expanduser().resolve()
        if args.python_runtime_root
        else resolve_python_runtime_root(repo_root / ".venv/bin/python")
    )
    python_site_packages_path = (
        Path(args.python_site_packages_path).expanduser().resolve()
        if args.python_site_packages_path
        else resolve_site_packages_root(repo_root)
    )
    manifest = write_unsigned_macos_app_bundle(
        repo_root=repo_root,
        executable_path=menubar_binary,
        swift_text_worker_executable_path=swift_worker_binary,
        python_runtime_root=python_runtime_root,
        python_site_packages_path=python_site_packages_path,
        output_path=args.output_path,
        app_name=args.app_name,
        bundle_id=args.bundle_id,
        version=args.version,
    )
    if args.archive_path:
        manifest["archive_path"] = str(
            archive_macos_app_bundle(manifest["app_path"], args.archive_path)
        )

    if args.json:
        print(json.dumps(manifest, indent=2, sort_keys=True))
    else:
        print(manifest["app_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
