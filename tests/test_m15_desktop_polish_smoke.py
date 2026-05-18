from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "m15_desktop_polish_smoke.py"
MODULE_SPEC = importlib.util.spec_from_file_location("m15_desktop_polish_smoke", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
m15_desktop_polish_smoke = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(m15_desktop_polish_smoke)


def test_run_smoke_projects_the_swift_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        m15_desktop_polish_smoke,
        "run_swift_smoke",
        lambda repo_root: {
            "chat": {"presentation_lag_ms": 24.0, "presentation_flush_count": 3},
            "signals": {
                "top_banner_title": "Download Recovery Available",
                "download_recovery_visible": 1,
                "update_signal_visible": 1,
                "update_signal_dismissible": 1,
            },
            "persistence": {
                "operator_session_restore_ms": 2.0,
                "operator_session_persist_write_ms": 1.0,
                "persisted_download_queue_count": 1,
                "restored_download_queue_count": 1,
                "restored_selected_tool_section": "Downloads",
            },
            "navigation": {
                "grounded_surface_count": 5,
                "grounded_tool_section_count": 10,
            },
        },
    )

    payload = m15_desktop_polish_smoke.run_smoke(tmp_path)

    assert payload["ok"] is True
    assert payload["repo_root"] == str(tmp_path)
    assert payload["chat"]["presentation_flush_count"] == 3
    assert payload["signals"]["download_recovery_visible"] is True
    assert payload["signals"]["update_signal_dismissible"] is True
    assert payload["persistence"]["restored_selected_tool_section"] == "Downloads"
    assert payload["navigation"]["grounded_surface_count"] == 5


def test_main_prints_machine_readable_payload(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        m15_desktop_polish_smoke,
        "run_smoke",
        lambda repo_root: {"ok": True, "repo_root": str(repo_root), "signals": {"download_recovery_visible": True}},
    )
    monkeypatch.setattr(
        m15_desktop_polish_smoke.sys,
        "argv",
        ["m15_desktop_polish_smoke.py", "--json", "--repo-root", str(tmp_path)],
    )

    assert m15_desktop_polish_smoke.main() == 0
    output = capsys.readouterr().out

    assert '"ok": true' in output
    assert str(tmp_path) in output


def test_main_prints_human_readable_payload(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        m15_desktop_polish_smoke,
        "run_smoke",
        lambda repo_root: {"ok": True, "repo_root": str(repo_root)},
    )
    monkeypatch.setattr(
        m15_desktop_polish_smoke.sys,
        "argv",
        ["m15_desktop_polish_smoke.py", "--repo-root", str(tmp_path)],
    )

    assert m15_desktop_polish_smoke.main() == 0
    output = capsys.readouterr().out

    assert "M15.4 desktop-polish smoke passed." in output
    assert str(tmp_path) in output


def test_run_swift_smoke_requires_marker(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class _Completed:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr(
        m15_desktop_polish_smoke.subprocess,
        "run",
        lambda *args, **kwargs: _Completed(),
    )

    with pytest.raises(RuntimeError, match="M15_DESKTOP_POLISH_SMOKE"):
        m15_desktop_polish_smoke.run_swift_smoke(tmp_path)
