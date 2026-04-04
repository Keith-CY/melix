from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "m8_startup_failure_smoke.py"
MODULE_SPEC = importlib.util.spec_from_file_location("m8_startup_failure_smoke", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
m8_startup_failure_smoke = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = m8_startup_failure_smoke
MODULE_SPEC.loader.exec_module(m8_startup_failure_smoke)


def test_main_emits_json_payload(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        m8_startup_failure_smoke,
        "main",
        m8_startup_failure_smoke.main,
    )
    monkeypatch.setattr(
        m8_startup_failure_smoke.sys,
        "argv",
        ["m8_startup_failure_smoke.py", "--json"],
    )

    assert m8_startup_failure_smoke.main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["checks"]["update_available"] is True
    assert payload["checks"]["startup_failure_classified"] is True
    assert payload["startup_failure"]["classification"] == "host_port_conflict"
