from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_module():
    module_path = REPO_ROOT / "scripts" / "m15_desktop_polish_smoke.py"
    module_spec = importlib.util.spec_from_file_location("m15_desktop_polish_smoke", module_path)
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def test_run_swift_smoke_uses_menubar_specific_swift_harness(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_module()
    monkeypatch.setattr(module.swift_root_package, "current_swift_toolchain_slug", lambda: "swift-6-3")
    captured: dict[str, object] = {}

    class _Completed:
        returncode = 0
        stdout = (
            'M15_DESKTOP_POLISH_SMOKE={"chat":{"presentation_lag_ms":1,"presentation_flush_count":2},'
            '"signals":{"top_banner_title":"Download Recovery Available","download_recovery_visible":1,'
            '"update_signal_visible":1,"update_signal_dismissible":1},'
            '"persistence":{"operator_session_restore_ms":3,"operator_session_persist_write_ms":4,'
            '"persisted_download_queue_count":1,"restored_download_queue_count":1,'
            '"restored_selected_tool_section":"downloads"},'
            '"navigation":{"grounded_surface_count":5,"grounded_tool_section_count":6}}\n'
        )
        stderr = ""

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["cwd"] = kwargs["cwd"]
        captured["env"] = kwargs["env"]
        return _Completed()

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.run_swift_smoke(tmp_path)

    assert payload["chat"]["presentation_lag_ms"] == 1
    assert captured["command"] == [
        "xcrun",
        "swift",
        "test",
        "--package-path",
        str(tmp_path / "apps" / "macos-menubar"),
        "--scratch-path",
        str(tmp_path / ".build" / "macos-menubar" / "swift-6-3"),
        "--disable-sandbox",
        "--filter",
        "DesktopPolishSmokeTests",
    ]
    assert captured["cwd"] == tmp_path
    env = captured["env"]
    assert env["HOME"] == str(tmp_path / ".swift-home" / "macos-menubar" / "swift-6-3")
    assert env["CLANG_MODULE_CACHE_PATH"] == str(
        tmp_path / ".build" / "ModuleCache.noindex" / "macos-menubar" / "swift-6-3"
    )
    assert env["MELIX_HOME"] == str(tmp_path / ".runtime" / "phase1" / "smoke-home")


def test_run_smoke_projects_payload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = _load_module()
    marker_payload = {
        "chat": {"presentation_lag_ms": 2, "presentation_flush_count": 3},
        "signals": {
            "top_banner_title": "Download Recovery Available",
            "download_recovery_visible": 1,
            "update_signal_visible": 1,
            "update_signal_dismissible": 1,
        },
        "persistence": {
            "operator_session_restore_ms": 4,
            "operator_session_persist_write_ms": 5,
            "persisted_download_queue_count": 1,
            "restored_download_queue_count": 1,
            "restored_selected_tool_section": "downloads",
        },
        "navigation": {"grounded_surface_count": 5, "grounded_tool_section_count": 6},
    }
    monkeypatch.setattr(module, "run_swift_smoke", lambda repo_root: marker_payload)

    payload = module.run_smoke(tmp_path)

    assert payload["ok"] is True
    assert payload["repo_root"] == str(tmp_path)
    assert payload["signals"]["top_banner_title"] == "Download Recovery Available"
    assert payload["signals"]["download_recovery_visible"] is True
    assert payload["persistence"]["restored_selected_tool_section"] == "downloads"
    assert payload["navigation"]["grounded_surface_count"] == 5


def test_run_swift_smoke_requires_marker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_module()

    class _Completed:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: _Completed())

    with pytest.raises(RuntimeError, match="M15_DESKTOP_POLISH_SMOKE"):
        module.run_swift_smoke(tmp_path)


def test_run_swift_smoke_retries_transient_swiftpm_lock_conflicts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_module()
    calls: list[list[str]] = []
    sleep_calls: list[float] = []

    class _Completed:
        def __init__(self, *, returncode: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    responses = [
        _Completed(
            returncode=1,
            stderr="Another instance of SwiftPM (PID: 12345) is already running using '/tmp/melix/apps/macos-menubar'",
        ),
        _Completed(
            returncode=0,
            stdout=(
                'M15_DESKTOP_POLISH_SMOKE={"chat":{"presentation_lag_ms":1,"presentation_flush_count":2},'
                '"signals":{"top_banner_title":"Download Recovery Available","download_recovery_visible":1,'
                '"update_signal_visible":1,"update_signal_dismissible":1},'
                '"persistence":{"operator_session_restore_ms":3,"operator_session_persist_write_ms":4,'
                '"persisted_download_queue_count":1,"restored_download_queue_count":1,'
                '"restored_selected_tool_section":"downloads"},'
                '"navigation":{"grounded_surface_count":5,"grounded_tool_section_count":6}}\n'
            ),
        ),
    ]

    def fake_run(command, **kwargs):
        calls.append(command)
        return responses.pop(0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module.time, "sleep", sleep_calls.append)

    payload = module.run_swift_smoke(tmp_path)

    assert payload["navigation"]["grounded_surface_count"] == 5
    assert len(calls) == 2
    assert sleep_calls == [module._SWIFTPM_LOCK_BACKOFF_SECONDS]
