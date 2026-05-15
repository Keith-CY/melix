from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "m13_api_onboarding_smoke.py"
MODULE_SPEC = importlib.util.spec_from_file_location("m13_api_onboarding_smoke", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
m13_api_onboarding_smoke = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(m13_api_onboarding_smoke)


def test_api_onboarding_smoke_verifies_the_live_quick_start_examples() -> None:
    payload = m13_api_onboarding_smoke.run_smoke(Path(__file__).resolve().parents[2])

    assert payload["ok"] is True
    assert payload["examples"]["input"] == "Hello from Melix"
    assert payload["examples"]["anthropic_version"] == "2023-06-01"
    assert payload["examples"]["auth_header_names"] == ["x-api-key"]
    assert payload["health"]["status_code"] == 200
    assert payload["health_diagnostics"]["status_code"] == 200
    assert payload["health_diagnostics"]["swift_text_ready"] is True
    assert payload["responses"]["status_code"] == 200
    assert payload["responses"]["contains_output_delta"] is True
    assert payload["responses"]["contains_completed_event"] is True
    assert payload["messages"]["status_code"] == 200
    assert payload["messages"]["contains_delta_event"] is True
    assert payload["messages"]["contains_completed_event"] is True
