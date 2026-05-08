from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "capture_macos_app_screenshots.py"
PNG_BYTES = b"\x89PNG\r\n\x1a\nfixture"


def load_capture_module():
    assert MODULE_PATH.exists(), f"Expected screenshot capture entrypoint at {MODULE_PATH}"
    spec = importlib.util.spec_from_file_location("melix_capture_macos_app_screenshots", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(spec.name, None)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def install_fake_run_command(module: Any, tmp_path: Path, calls: list[dict[str, Any]]) -> None:
    def fake_run_command(
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(
            {
                "command": command,
                "cwd": cwd,
                "env": dict(env or {}),
                "capture_output": capture_output,
            }
        )

        if len(command) >= 2 and command[1] == "scripts/package_macos_menubar_app.py":
            output_path = Path(command[command.index("--output-path") + 1])
            menubar_binary = output_path / "Contents" / "Resources" / "melix-menubar"
            menubar_binary.parent.mkdir(parents=True, exist_ok=True)
            menubar_binary.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            payload = {
                "app_path": str(output_path),
                "bundled_binary_path": str(menubar_binary),
            }
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

        if command and command[0].endswith("melix-menubar"):
            assert env is not None
            output_dir = Path(env["MELIX_APP_SCREENSHOT_OUTPUT_DIR"])
            screenshot_root = output_dir / "screenshots"
            screenshot_root.mkdir(parents=True, exist_ok=True)
            screenshot_path = screenshot_root / "workspace-chat.png"
            screenshot_path.write_bytes(PNG_BYTES)
            manifest_path = output_dir / "screenshot_manifest.json"
            payload = {
                "schema_version": "melix.app_screenshots.v1",
                "manifest_path": str(manifest_path),
                "app_path": env["MELIX_APP_SCREENSHOT_APP_PATH"],
                "output_directory_path": str(output_dir),
                "screenshot_root": str(screenshot_root),
                "width": int(env["MELIX_APP_SCREENSHOT_WIDTH"]),
                "height": int(env["MELIX_APP_SCREENSHOT_HEIGHT"]),
                "screenshots": [
                    {
                        "id": "workspace-chat",
                        "kind": "workspace",
                        "surface": "Chat",
                        "tool_section": "",
                        "path": str(screenshot_path),
                        "render_ms": 1.25,
                    }
                ],
            }
            manifest_path.write_text(json.dumps(payload), encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    module.run_command = fake_run_command


def test_run_command_executes_subprocess_with_captured_output(tmp_path: Path) -> None:
    module = load_capture_module()

    completed = module.run_command(
        [sys.executable, "-c", "print('melix screenshots')"],
        cwd=tmp_path,
        capture_output=True,
    )

    assert completed.stdout == "melix screenshots\n"


def test_default_output_dir_uses_temp_screenshot_prefix() -> None:
    module = load_capture_module()

    output_dir = module.default_output_dir()

    try:
        assert output_dir.name.startswith("melix-app-screenshots-")
        assert output_dir.is_dir()
    finally:
        output_dir.rmdir()


def test_package_python_executable_prefers_repo_virtualenv(tmp_path: Path) -> None:
    module = load_capture_module()
    repo_python = tmp_path / ".venv" / "bin" / "python"
    repo_python.parent.mkdir(parents=True)
    repo_python.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    assert module.package_python_executable(tmp_path) == repo_python


def test_resolve_menubar_binary_reports_missing_bundle_binary(tmp_path: Path) -> None:
    module = load_capture_module()

    with pytest.raises(FileNotFoundError, match="Missing bundled menubar binary"):
        module.resolve_menubar_binary(tmp_path / "Melix.app")


def test_run_capture_builds_packages_and_captures_app_screenshots(tmp_path: Path) -> None:
    module = load_capture_module()
    calls: list[dict[str, Any]] = []
    install_fake_run_command(module, tmp_path, calls)

    payload = module.run_capture(
        repo_root=tmp_path,
        output_dir=tmp_path / "capture",
        skip_build=False,
        width=800,
        height=500,
    )

    commands = [call["command"] for call in calls]
    assert commands[0][:4] == ["uv", "sync", "--project", "services/mlx-worker-python"]
    assert commands[1][:4] == ["xcrun", "swift", "build", "--product"]
    assert commands[2][:5] == ["xcrun", "swift", "build", "--package-path", "services/mlx-text-worker-swift"]
    assert commands[3][:5] == ["xcrun", "swift", "build", "--package-path", "apps/macos-menubar"]
    assert commands[4][1] == "scripts/package_macos_menubar_app.py"
    assert commands[5][0].endswith("Melix.app/Contents/Resources/melix-menubar")
    assert calls[0]["env"]["UV_PROJECT_ENVIRONMENT"] == str(tmp_path / ".venv")
    assert calls[5]["env"]["MELIX_APP_SCREENSHOT_CAPTURE"] == "1"
    assert calls[5]["env"]["MELIX_APP_SCREENSHOT_WIDTH"] == "800"
    assert calls[5]["env"]["MELIX_APP_SCREENSHOT_HEIGHT"] == "500"
    assert payload["ok"] is True
    assert payload["screenshot_count"] == 1
    assert payload["screenshots"][0]["id"] == "workspace-chat"


def test_run_capture_skip_build_still_packages_and_captures(tmp_path: Path) -> None:
    module = load_capture_module()
    calls: list[dict[str, Any]] = []
    install_fake_run_command(module, tmp_path, calls)

    module.run_capture(
        repo_root=tmp_path,
        output_dir=tmp_path / "capture",
        skip_build=True,
        width=1440,
        height=960,
    )

    commands = [call["command"] for call in calls]
    assert all(command[:2] != ["uv", "sync"] for command in commands)
    assert all(command[:3] != ["xcrun", "swift", "build"] for command in commands)
    assert commands[0][1] == "scripts/package_macos_menubar_app.py"
    assert commands[1][0].endswith("Melix.app/Contents/Resources/melix-menubar")


def test_validate_capture_manifest_rejects_missing_png(tmp_path: Path) -> None:
    module = load_capture_module()
    payload = {
        "schema_version": "melix.app_screenshots.v1",
        "screenshots": [{"path": str(tmp_path / "missing.png")}],
    }

    with pytest.raises(RuntimeError, match="Screenshot file is missing"):
        module.validate_capture_manifest(payload)


def test_validate_capture_manifest_rejects_malformed_entries(tmp_path: Path) -> None:
    module = load_capture_module()
    non_png_path = tmp_path / "not-a-png.txt"
    non_png_path.write_text("not png", encoding="utf-8")

    malformed_payloads = [
        ({}, "unexpected schema_version"),
        ({"schema_version": "melix.app_screenshots.v1", "screenshots": []}, "does not contain screenshots"),
        (
            {"schema_version": "melix.app_screenshots.v1", "screenshots": [{}]},
            "entry without a path",
        ),
        (
            {
                "schema_version": "melix.app_screenshots.v1",
                "screenshots": [{"path": str(non_png_path)}],
            },
            "is not a PNG",
        ),
    ]

    for payload, message in malformed_payloads:
        with pytest.raises(RuntimeError, match=message):
            module.validate_capture_manifest(payload)


def test_main_json_emits_capture_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_capture_module()

    def fake_run_capture(**kwargs):
        return {
            "ok": True,
            "output_dir": str(kwargs["output_dir"]),
            "app_path": str(kwargs["output_dir"] / "Melix.app"),
            "screenshot_manifest_path": str(kwargs["output_dir"] / "screenshot_manifest.json"),
            "screenshot_root": str(kwargs["output_dir"] / "screenshots"),
            "screenshot_count": 12,
            "screenshots": [],
            "package_manifest": {},
        }

    monkeypatch.setattr(module, "run_capture", fake_run_capture)

    result = module.main(
        [
            "--repo-root",
            str(tmp_path / "repo"),
            "--output-dir",
            str(tmp_path / "capture"),
            "--skip-build",
            "--json",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["screenshot_count"] == 12


def test_main_rejects_non_positive_dimensions() -> None:
    module = load_capture_module()

    with pytest.raises(SystemExit) as error:
        module.main(["--width", "0"])

    assert str(error.value) == "--width and --height must be positive integers."


def test_main_text_output_uses_default_output_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_capture_module()
    output_dir = tmp_path / "default-capture"

    def fake_run_capture(**kwargs):
        assert kwargs["output_dir"] == output_dir
        return {
            "ok": True,
            "output_dir": str(output_dir),
            "app_path": str(output_dir / "Melix.app"),
            "screenshot_manifest_path": str(output_dir / "screenshot_manifest.json"),
            "screenshot_root": str(output_dir / "screenshots"),
            "screenshot_count": 3,
            "screenshots": [],
            "package_manifest": {},
        }

    monkeypatch.setattr(module, "default_output_dir", lambda: output_dir)
    monkeypatch.setattr(module, "run_capture", fake_run_capture)

    assert module.main(["--repo-root", str(tmp_path / "repo"), "--skip-build"]) == 0

    output = capsys.readouterr().out
    assert f"Melix app screenshots: {output_dir / 'screenshots'}" in output
    assert f"Manifest: {output_dir / 'screenshot_manifest.json'}" in output
    assert "Screenshots: 3" in output


def test_main_reports_called_process_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_capture_module()

    def fake_run_capture(**kwargs):
        raise subprocess.CalledProcessError(
            returncode=17,
            cmd=["melix-menubar"],
            output="partial stdout\n",
            stderr="failure stderr\n",
        )

    monkeypatch.setattr(module, "run_capture", fake_run_capture)

    result = module.main(["--repo-root", str(tmp_path), "--output-dir", str(tmp_path / "capture")])

    assert result == 1
    error_output = capsys.readouterr().err
    assert "returned non-zero exit status 17" in error_output
    assert "stdout:\npartial stdout" in error_output
    assert "stderr:\nfailure stderr" in error_output


def test_main_reports_runtime_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_capture_module()

    def fake_run_capture(**kwargs):
        raise RuntimeError("manifest failed")

    monkeypatch.setattr(module, "run_capture", fake_run_capture)

    result = module.main(["--repo-root", str(tmp_path), "--output-dir", str(tmp_path / "capture")])

    assert result == 1
    assert "manifest failed" in capsys.readouterr().err
