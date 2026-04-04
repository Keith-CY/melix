from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "m9_connection_smoke.py"
MODULE_SPEC = importlib.util.spec_from_file_location("m9_connection_smoke", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
m9_connection_smoke = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(m9_connection_smoke)


def test_run_smoke_aggregates_scenario_metrics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        m9_connection_smoke,
        "run_keepalive_scenario",
        lambda repo_root: {"status": 200, "request_id": "req-keepalive", "saw_keepalive": True},
    )
    monkeypatch.setattr(
        m9_connection_smoke,
        "run_resume_scenario",
        lambda repo_root: {
            "status": 200,
            "request_id": "req-resume",
            "recovered_request_id": "req-resume",
            "metrics": {
                "disconnect.keepalive_gap_ms": 5.0,
                "disconnect.recovery_latency_ms": 12.5,
                "disconnect.resume_success_rate": 100.0,
            },
        },
    )
    monkeypatch.setattr(
        m9_connection_smoke,
        "run_terminal_failure_scenario",
        lambda repo_root: {
            "request_id": "req-terminal",
            "resume_status": 409,
            "resume_error_code": "request_not_resumable",
            "metrics": {"disconnect.terminal_failure_count": 1.0},
        },
    )

    payload = m9_connection_smoke.run_smoke(tmp_path)

    assert payload["ok"] is True
    assert payload["metrics"]["disconnect.resume_success_rate"] == 100.0
    assert payload["metrics"]["disconnect.terminal_failure_count"] == 1.0
    assert payload["scenarios"]["terminal_failure"]["resume_error_code"] == "request_not_resumable"


def test_main_prints_machine_readable_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(
        m9_connection_smoke,
        "run_smoke",
        lambda repo_root: {
            "ok": True,
            "metrics": {"disconnect.resume_success_rate": 100.0},
            "scenarios": {"resume": {"request_id": "req-resume"}},
            "repo_root": str(repo_root),
        },
    )
    monkeypatch.setattr(
        m9_connection_smoke.sys,
        "argv",
        ["m9_connection_smoke.py", "--json", "--repo-root", str(tmp_path)],
    )

    assert m9_connection_smoke.main() == 0
    output = capsys.readouterr().out

    assert '"ok": true' in output
    assert '"disconnect.resume_success_rate": 100.0' in output


def test_wait_for_metric_times_out_when_metric_never_arrives(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    values = iter([0.0, 0.0, 1.0])
    sleeps: list[float] = []

    monkeypatch.setattr(m9_connection_smoke.time, "time", lambda: next(values))
    monkeypatch.setattr(m9_connection_smoke.time, "sleep", lambda seconds: sleeps.append(seconds))

    with pytest.raises(RuntimeError, match="timed out waiting for metric missing"):
        m9_connection_smoke.wait_for_metric(tmp_path / "missing.json", "missing", minimum=1, timeout_seconds=0.5)

    assert sleeps == [0.1]
