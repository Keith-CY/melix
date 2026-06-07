from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import phase8_release_gate
import phase8_runtime_probes
from worker.productization import release_gates as release_gates_module


def test_make_phase8_release_gate_keeps_redirected_output_json_clean() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    target = makefile.split("\nphase8-release-gate:\n", 1)[1].split("\nphase8-metrics:", 1)[0]
    target_lines = target.splitlines()

    assert '\t@mkdir -p "$(UV_CACHE_DIR)"' in target_lines
    assert any(
        line.startswith('\t@PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python"')
        for line in target_lines
    )


def test_phase8_release_gate_main_emits_json_and_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(phase8_release_gate, "load_release_gate_policy", lambda path: {"runtime_core": {}})
    monkeypatch.setattr(
        phase8_release_gate,
        "collect_restart_recovery_evidence",
        lambda repo_root: {"restart_recovery_ms": 500.0, "restart_recovery_success_rate": 100.0},
    )
    monkeypatch.setattr(
        phase8_release_gate,
        "collect_runtime_core_evidence",
        lambda repo_root: {
            "multi_model_ready_count": 3.0,
            "multi_model_request_success_rate": 100.0,
            "prefill_memory_guard_rejection_count": 1.0,
            "prefill_memory_guard_success_rate": 100.0,
        },
    )
    monkeypatch.setattr(
        phase8_release_gate,
        "build_release_gate_report",
        lambda repo_root, policy, recovery, runtime_core: {
            "recovery": recovery,
            "runtime_core": runtime_core,
            "passed": True,
            "failures": [],
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["phase8_release_gate.py", "--repo-root", str(tmp_path), "--json"],
    )

    assert phase8_release_gate.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["passed"] is True
    assert payload["runtime_core"]["multi_model_ready_count"] == 3.0


def test_phase8_release_gate_main_returns_nonzero_without_json_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(phase8_release_gate, "load_release_gate_policy", lambda path: {"runtime_core": {}})
    monkeypatch.setattr(
        phase8_release_gate,
        "collect_restart_recovery_evidence",
        lambda repo_root: {"restart_recovery_ms": 900.0, "restart_recovery_success_rate": 0.0},
    )
    monkeypatch.setattr(
        phase8_release_gate,
        "collect_runtime_core_evidence",
        lambda repo_root: {
            "multi_model_ready_count": 2.0,
            "multi_model_request_success_rate": 66.0,
            "prefill_memory_guard_rejection_count": 0.0,
            "prefill_memory_guard_success_rate": 0.0,
        },
    )
    monkeypatch.setattr(
        phase8_release_gate,
        "build_release_gate_report",
        lambda repo_root, policy, recovery, runtime_core: {
            "recovery": recovery,
            "runtime_core": runtime_core,
            "passed": False,
            "failures": ["runtime_core evidence regressed"],
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["phase8_release_gate.py", "--repo-root", str(tmp_path)],
    )

    assert phase8_release_gate.main() == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["passed"] is False
    assert payload["failures"] == ["runtime_core evidence regressed"]


def test_phase8_release_gate_run_path_exits_through_main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        phase8_runtime_probes,
        "collect_restart_recovery_evidence",
        lambda repo_root: {"restart_recovery_ms": 500.0, "restart_recovery_success_rate": 100.0},
    )
    monkeypatch.setattr(
        phase8_runtime_probes,
        "collect_runtime_core_evidence",
        lambda repo_root: {
            "multi_model_ready_count": 3.0,
            "multi_model_request_success_rate": 100.0,
            "prefill_memory_guard_rejection_count": 1.0,
            "prefill_memory_guard_success_rate": 100.0,
        },
    )
    monkeypatch.setattr(release_gates_module, "load_release_gate_policy", lambda path: {"runtime_core": {}})
    monkeypatch.setattr(
        release_gates_module,
        "build_release_gate_report",
        lambda repo_root, policy, recovery, runtime_core: {
            "recovery": recovery,
            "runtime_core": runtime_core,
            "passed": True,
            "failures": [],
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["phase8_release_gate.py", "--repo-root", str(tmp_path), "--json"],
    )

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(ROOT / "scripts" / "phase8_release_gate.py"), run_name="__main__")

    assert excinfo.value.code == 0
