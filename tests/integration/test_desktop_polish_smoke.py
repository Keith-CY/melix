from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "m15_desktop_polish_smoke.py"
MODULE_SPEC = importlib.util.spec_from_file_location("m15_desktop_polish_smoke", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
m15_desktop_polish_smoke = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(m15_desktop_polish_smoke)


def test_desktop_polish_smoke_verifies_navigation_signals_and_queue_restore() -> None:
    payload = m15_desktop_polish_smoke.run_smoke(Path(__file__).resolve().parents[2])

    assert payload["ok"] is True
    assert payload["chat"]["presentation_lag_ms"] >= 0
    assert payload["chat"]["presentation_flush_count"] > 1
    assert payload["signals"]["top_banner_title"] == "Download Recovery Available"
    assert payload["signals"]["download_recovery_visible"] is True
    assert payload["signals"]["update_signal_visible"] is True
    assert payload["signals"]["update_signal_dismissible"] is True
    assert payload["persistence"]["persisted_download_queue_count"] == 1
    assert payload["persistence"]["restored_download_queue_count"] == 1
    assert payload["persistence"]["restored_selected_tool_section"] == "Downloads"
    assert payload["navigation"]["grounded_surface_count"] == 5
    assert payload["navigation"]["grounded_tool_section_count"] == 6
