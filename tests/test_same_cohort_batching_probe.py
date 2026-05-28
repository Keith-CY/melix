from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "same_cohort_batching_probe.py"
MODULE_SPEC = importlib.util.spec_from_file_location("same_cohort_batching_probe", MODULE_PATH)
assert MODULE_SPEC and MODULE_SPEC.loader
probe = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(probe)


def raw_probe_payload(*, admission_batch_size: int, worker_batch_size: int) -> dict:
    return {
        "admission": {
            "scheduler_continuous_batch_size": admission_batch_size,
            "scheduler_continuous_batch_active_cohorts": 1,
        },
        "worker": {
            "decode_request_ids": ["req-same-cohort-1", "req-same-cohort-2"],
            "max_model_step_batch_size": worker_batch_size,
        },
        "request_links": [
            {
                "gateway_request_id": "req-same-cohort-1",
                "coordinator_request_id": "req-same-cohort-1",
                "worker_prefill_request_id": "req-same-cohort-1",
                "worker_decode_request_id": "req-same-cohort-1",
            },
            {
                "gateway_request_id": "req-same-cohort-2",
                "coordinator_request_id": "req-same-cohort-2",
                "worker_prefill_request_id": "req-same-cohort-2",
                "worker_decode_request_id": "req-same-cohort-2",
            },
        ],
    }


def test_warns_when_admission_batches_but_worker_batch_size_is_singleton() -> None:
    analyzed = probe.analyze_probe(
        raw_probe_payload(admission_batch_size=2, worker_batch_size=1)
    )

    assert analyzed["status"] == "warning"
    assert analyzed["warnings"][0]["code"] == "admission_batch_without_worker_model_batch"
    assert analyzed["failures"] == []


def test_passes_when_worker_model_step_batch_matches_admission_batch() -> None:
    analyzed = probe.analyze_probe(
        raw_probe_payload(admission_batch_size=2, worker_batch_size=2)
    )

    assert analyzed["status"] == "passed"
    assert analyzed["warnings"] == []
    assert analyzed["failures"] == []


def test_fails_when_request_links_do_not_cover_worker_decode_requests() -> None:
    raw = raw_probe_payload(admission_batch_size=2, worker_batch_size=1)
    raw["worker"]["decode_request_ids"] = ["req-same-cohort-1"]

    analyzed = probe.analyze_probe(raw)

    assert analyzed["status"] == "failed"
    assert analyzed["failures"][0]["code"] == "missing_worker_decode_request_ids"


def test_fails_when_two_request_links_are_missing() -> None:
    raw = raw_probe_payload(admission_batch_size=2, worker_batch_size=1)
    raw["request_links"] = raw["request_links"][:1]

    analyzed = probe.analyze_probe(raw)

    assert analyzed["status"] == "failed"
    assert analyzed["failures"][0]["code"] == "missing_request_links"


def test_fails_when_scheduler_batch_is_not_observed() -> None:
    analyzed = probe.analyze_probe(
        raw_probe_payload(admission_batch_size=1, worker_batch_size=1)
    )

    assert analyzed["status"] == "failed"
    assert analyzed["failures"][0]["code"] == "admission_batch_not_observed"


def test_fails_when_worker_model_step_batch_is_missing() -> None:
    analyzed = probe.analyze_probe(
        raw_probe_payload(admission_batch_size=2, worker_batch_size=0)
    )

    assert analyzed["status"] == "failed"
    assert analyzed["failures"][0]["code"] == "worker_model_step_batch_missing"


def test_main_analyzes_input_file_and_writes_output(tmp_path, monkeypatch) -> None:
    input_path = tmp_path / "raw.json"
    output_path = tmp_path / "analyzed.json"
    input_path.write_text(
        json.dumps(raw_probe_payload(admission_batch_size=2, worker_batch_size=1)),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "same_cohort_batching_probe.py",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ],
    )

    assert probe.main() == 0
    analyzed = json.loads(output_path.read_text(encoding="utf-8"))
    assert analyzed["status"] == "warning"


def test_main_can_fail_on_warning(tmp_path, monkeypatch) -> None:
    input_path = tmp_path / "raw.json"
    input_path.write_text(
        json.dumps(raw_probe_payload(admission_batch_size=2, worker_batch_size=1)),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "same_cohort_batching_probe.py",
            "--input",
            str(input_path),
            "--fail-on-warning",
        ],
    )

    assert probe.main() == 2


def test_main_returns_failure_status_for_invalid_probe(tmp_path, monkeypatch) -> None:
    input_path = tmp_path / "raw.json"
    input_path.write_text(
        json.dumps(raw_probe_payload(admission_batch_size=1, worker_batch_size=1)),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "same_cohort_batching_probe.py",
            "--input",
            str(input_path),
        ],
    )

    assert probe.main() == 1


def test_run_swift_probe_extracts_prefixed_json(monkeypatch) -> None:
    raw = raw_probe_payload(admission_batch_size=2, worker_batch_size=1)

    def fake_run(command, cwd, env, text, stdout, stderr, check):
        assert command[-1] == "focused-filter"
        assert env["MELIX_SAME_COHORT_BATCHING_PROBE"] == "1"
        assert text is True
        assert stdout is subprocess.PIPE
        assert stderr is subprocess.STDOUT
        assert check is False
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="noise\n"
            f"{probe.PROBE_PREFIX}{json.dumps(raw)}\n",
        )

    monkeypatch.setattr(probe.subprocess, "run", fake_run)

    assert probe.run_swift_probe("focused-filter") == raw


def test_run_swift_probe_raises_when_swift_fails(monkeypatch) -> None:
    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["swift", "test"],
            returncode=1,
            stdout="compile failed",
        )

    monkeypatch.setattr(probe.subprocess, "run", fake_run)

    try:
        probe.run_swift_probe("focused-filter")
    except RuntimeError as exc:
        assert "compile failed" in str(exc)
    else:
        raise AssertionError("Expected run_swift_probe to raise on Swift failure.")


def test_run_swift_probe_raises_when_json_is_missing(monkeypatch) -> None:
    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["swift", "test"],
            returncode=0,
            stdout="test passed without payload",
        )

    monkeypatch.setattr(probe.subprocess, "run", fake_run)

    try:
        probe.run_swift_probe("focused-filter")
    except RuntimeError as exc:
        assert probe.PROBE_PREFIX in str(exc)
    else:
        raise AssertionError("Expected run_swift_probe to raise when JSON is missing.")
