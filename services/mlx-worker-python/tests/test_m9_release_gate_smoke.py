from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[3] / "scripts" / "m9_release_gate_smoke.py"
REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_SPEC = importlib.util.spec_from_file_location("m9_release_gate_smoke", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
m9_release_gate_smoke = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(m9_release_gate_smoke)


def test_main_prints_passing_smoke_payload(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        m9_release_gate_smoke,
        "run_smoke",
        lambda repo_root, fixture_mode: {
            "passed": True,
            "fixture_mode": fixture_mode,
            "metrics": {
                "release_gate.m9_required_probe_count": 23.0,
                "release_gate.m9_missing_probe_count": 0.0,
                "release_gate.m9_failed_threshold_count": 0.0,
                "release_gate.observability_required_artifact_validity_passed": 1.0,
            },
        },
    )
    monkeypatch.setattr(
        m9_release_gate_smoke.sys,
        "argv",
        ["m9_release_gate_smoke.py", "--repo-root", str(tmp_path), "--json"],
    )

    assert m9_release_gate_smoke.main() == 0
    output = capsys.readouterr().out

    assert '"passed": true' in output
    assert '"release_gate.m9_required_probe_count": 23.0' in output
    assert '"release_gate.observability_required_artifact_validity_passed": 1.0' in output


def test_main_returns_nonzero_for_failing_fixture(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        m9_release_gate_smoke,
        "run_smoke",
        lambda repo_root, fixture_mode: {
            "passed": False,
            "fixture_mode": fixture_mode,
            "metrics": {
                "release_gate.m9_required_probe_count": 23.0,
                "release_gate.m9_missing_probe_count": 1.0,
                "release_gate.m9_failed_threshold_count": 2.0,
            },
            "failures": ["m9.shared_access.shared_access.accepted_client_count is missing"],
        },
    )
    monkeypatch.setattr(
        m9_release_gate_smoke.sys,
        "argv",
        [
            "m9_release_gate_smoke.py",
            "--repo-root",
            str(tmp_path),
            "--fixture-mode",
            "failing",
            "--json",
        ],
    )

    assert m9_release_gate_smoke.main() == 1
    output = capsys.readouterr().out

    assert '"passed": false' in output
    assert '"release_gate.m9_missing_probe_count": 1.0' in output


def test_run_smoke_passes_for_passing_fixture() -> None:
    payload = m9_release_gate_smoke.run_smoke(REPO_ROOT, "passing")

    assert payload["passed"] is True
    assert payload["metrics"]["release_gate.observability_required_artifact_validity_passed"] == 1.0
