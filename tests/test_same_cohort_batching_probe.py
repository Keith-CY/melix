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


def test_fails_when_linked_decode_request_id_is_absent_from_worker_observations() -> None:
    raw = raw_probe_payload(admission_batch_size=2, worker_batch_size=1)
    raw["worker"]["decode_request_ids"] = ["req-same-cohort-1"]

    analyzed = probe.analyze_probe(raw)

    assert analyzed["status"] == "failed"
    assert analyzed["failures"][0]["code"] == "missing_worker_decode_request_ids"


def test_ignores_empty_or_none_decode_request_ids() -> None:
    raw = raw_probe_payload(admission_batch_size=2, worker_batch_size=1)
    raw["worker"]["decode_request_ids"] = [
        "req-same-cohort-1",
        None,
        "  ",
    ]
    raw["request_links"][1]["worker_decode_request_id"] = None

    analyzed = probe.analyze_probe(raw)

    assert analyzed["status"] == "warning"
    assert analyzed["failures"] == []


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


def test_probe_metrics_flattens_warning_evidence() -> None:
    raw = raw_probe_payload(admission_batch_size=2, worker_batch_size=1)
    raw["worker"]["decode_loop_iterations"] = 2
    analyzed = probe.analyze_probe(raw)

    metrics = probe.probe_metrics(analyzed)

    assert metrics == {
        "status_passed": 0.0,
        "status_warning": 1.0,
        "status_failed": 0.0,
        "warning_count": 1.0,
        "failure_count": 0.0,
        "scheduler_continuous_batch_size": 2.0,
        "scheduler_active_cohorts": 1.0,
        "worker_max_model_step_batch_size": 1.0,
        "worker_decode_loop_iterations": 2.0,
        "linked_request_count": 2.0,
        "scheduler_to_worker_batch_delta": 1.0,
    }


def test_main_metrics_emits_numeric_json(tmp_path, monkeypatch, capsys) -> None:
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
            "--metrics",
        ],
    )

    assert probe.main() == 0
    metrics = json.loads(capsys.readouterr().out)
    assert all(isinstance(value, (int, float)) for value in metrics.values())
    assert metrics["status_warning"] == 1.0
    assert metrics["scheduler_to_worker_batch_delta"] == 1.0


def test_main_metrics_returns_failure_for_failed_probe(tmp_path, monkeypatch, capsys) -> None:
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
            "--metrics",
        ],
    )

    assert probe.main() == 1
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["status_failed"] == 1.0
    assert metrics["failure_count"] == 1.0


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


def test_non_numeric_batch_fields_are_treated_as_missing() -> None:
    raw = raw_probe_payload(admission_batch_size=2, worker_batch_size=1)
    raw["admission"]["scheduler_continuous_batch_size"] = "two"
    raw["worker"]["max_model_step_batch_size"] = True

    analyzed = probe.analyze_probe(raw)

    assert analyzed["status"] == "failed"
    failure_codes = {failure["code"] for failure in analyzed["failures"]}
    assert "admission_batch_not_observed" in failure_codes
    assert "worker_model_step_batch_missing" in failure_codes


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


def test_run_swift_probe_wraps_malformed_json(monkeypatch) -> None:
    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["swift", "test"],
            returncode=0,
            stdout=f"{probe.PROBE_PREFIX}{{not-json}}\n",
        )

    monkeypatch.setattr(probe.subprocess, "run", fake_run)

    try:
        probe.run_swift_probe("focused-filter")
    except RuntimeError as exc:
        assert "Failed to parse same-cohort probe JSON payload" in str(exc)
        assert "{not-json}" in str(exc)
    else:
        raise AssertionError("Expected run_swift_probe to wrap malformed JSON.")


def test_run_swift_probe_wraps_missing_swift_cli(monkeypatch) -> None:
    def fake_run(*_args, **_kwargs):
        raise FileNotFoundError("swift")

    monkeypatch.setattr(probe.subprocess, "run", fake_run)

    try:
        probe.run_swift_probe("focused-filter")
    except RuntimeError as exc:
        assert "Swift CLI" in str(exc)
    else:
        raise AssertionError("Expected run_swift_probe to wrap a missing Swift CLI.")


def test_main_returns_error_for_missing_input_file(tmp_path, monkeypatch, capsys) -> None:
    missing_path = tmp_path / "missing.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "same_cohort_batching_probe.py",
            "--input",
            str(missing_path),
        ],
    )

    assert probe.main() == 1
    captured = capsys.readouterr()
    assert "Input probe JSON file does not exist" in captured.err


def test_main_returns_error_for_malformed_input_json(tmp_path, monkeypatch, capsys) -> None:
    input_path = tmp_path / "malformed.json"
    input_path.write_text("{bad-json}", encoding="utf-8")
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
    captured = capsys.readouterr()
    assert "Failed to parse input probe JSON file" in captured.err


def test_main_returns_error_for_non_object_input_json(tmp_path, monkeypatch, capsys) -> None:
    input_path = tmp_path / "array.json"
    input_path.write_text("[]", encoding="utf-8")
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
    captured = capsys.readouterr()
    assert "must contain a JSON object" in captured.err


def test_main_returns_error_when_output_write_fails(tmp_path, monkeypatch, capsys) -> None:
    input_path = tmp_path / "raw.json"
    input_path.write_text(
        json.dumps(raw_probe_payload(admission_batch_size=2, worker_batch_size=1)),
        encoding="utf-8",
    )
    output_dir = tmp_path / "existing-file"
    output_dir.write_text("not a directory", encoding="utf-8")
    output_path = output_dir / "analyzed.json"
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

    assert probe.main() == 1
    captured = capsys.readouterr()
    assert "failed to write output file" in captured.err
