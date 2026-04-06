from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "m8_packaging_target_smoke.py"


def load_packaging_target_smoke_module():
    assert MODULE_PATH.exists(), f"Expected packaging target smoke entrypoint at {MODULE_PATH}"
    spec = importlib.util.spec_from_file_location("melix_m8_packaging_target_smoke", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(spec.name, None)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_main_emits_expected_packaging_target_metrics(
    monkeypatch,
    capsys,
) -> None:
    module = load_packaging_target_smoke_module()
    monkeypatch.setattr(module.sys, "argv", ["m8_packaging_target_smoke.py", "--json"])

    assert module.main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["packaging_target_profile_count"] == 3
    assert payload["packaging_target_shared_identity_ok"] == 1
    assert payload["packaging_target_distinct_packaging_kind_count"] == 3
    assert payload["packaging_target_launch_agents_profile_ok"] == 1
    assert payload["packaging_target_homebrew_profile_ok"] == 1
    assert payload["packaging_target_app_bundle_profile_ok"] == 1
