from __future__ import annotations

import json
import platform
from pathlib import Path
from types import SimpleNamespace

from worker.productization import run_records
from worker.productization.run_records import (
    attach_run_record_write_probe,
    build_evaluation_run_record,
    build_serving_benchmark_run_record,
    write_run_record,
)


def test_serving_benchmark_run_record_redacts_sensitive_parameters_and_writes_probe(
    tmp_path: Path,
) -> None:
    job = SimpleNamespace(
        job_id="bench-secret",
        model_id="melix-dev-text",
        task_kind="text-generation",
        source_repo="HuggingFaceH4/ultrachat_200k",
        suites=("smoke",),
        context_lengths=(16,),
        generation_length=8,
        batch_sizes=(1,),
        repeats=1,
        cache_profile="cold",
        reasoning_mode="disabled",
        structured_output_mode="plain_text",
        parameters={
            "api_key": "sk-abcdefghi",
            "dataset_ref": "org/private-eval@main",
            "sample_size": "4",
            "batch_factor": "1",
            "schema_sha256": "abc123",
            "schema_size_bytes": "32",
            "hints_sha256": "def456",
            "hints_size_bytes": "24",
            "hints_format": "text",
            "request_metadata": {
                "authorization": "Bearer local-secret",
                "trace_id": "trace-1",
            },
        },
        status="completed",
        created_at_unix_ms=100,
        updated_at_unix_ms=150,
    )
    result = SimpleNamespace(
        metrics=(
            SimpleNamespace(name="bench.smoke.ttft_ms", value=12.5, unit="ms"),
            SimpleNamespace(name="bench.smoke.peak_memory_bytes", value=4096, unit="bytes"),
        )
    )
    artifact_paths = {
        "evidence": tmp_path / "run-evidence.json",
        "telemetry_jsonl": tmp_path / "telemetry-samples.jsonl",
    }

    record = build_serving_benchmark_run_record(
        job=job,
        results=(result,),
        artifact_root=tmp_path,
        artifact_paths=artifact_paths,
    )

    assert record["schema_version"] == "melix.run_record.v1"
    assert record["run_id"] == "bench-secret"
    assert record["run_kind"] == "benchmark"
    assert record["parameters"]["api_key"] == "[REDACTED]"
    assert record["parameters"]["request_metadata"] == {
        "authorization": "[REDACTED]",
        "trace_id": "trace-1",
    }
    assert record["command"]["redacted"] is True
    assert record["command"]["display"].startswith("melix bench run --model-id melix-dev-text")
    assert record["resources"]["peak_memory_bytes"] == 4096
    assert record["reproducibility"] == {
        "schema_sha256": "abc123",
        "schema_size_bytes": "32",
        "hints_sha256": "def456",
        "hints_size_bytes": "24",
        "hints_format": "text",
    }
    assert "Sensitive command or request values were redacted" in record["known_gaps"][0]
    assert "sk-abcdefghi" not in json.dumps(record)
    assert "local-secret" not in json.dumps(record)

    record_path = tmp_path / "run-record.json"
    persisted_path = write_run_record(
        record_path,
        attach_run_record_write_probe(record, duration_ms=1.23456),
    )
    payload = json.loads(record_path.read_text(encoding="utf-8"))

    assert persisted_path == record_path
    assert payload["probes"] == [
        {
            "component": "worker.productization.run_records",
            "phase": "run_record_write",
            "duration_ms": 1.2346,
            "status": "completed",
        }
    ]


def test_run_record_builders_cover_reproducibility_fallbacks_and_repo_targets(
    tmp_path: Path,
) -> None:
    job = SimpleNamespace(
        job_id="bench-repo",
        model_id="",
        task_kind="text-generation",
        source_repo="mlx-community/model",
        suites=("smoke",),
        context_lengths=(),
        generation_length=0,
        batch_sizes=(),
        repeats=0,
        cache_profile="",
        reasoning_mode="",
        structured_output_mode="",
        parameters={
            "notes": ["safe", "ghp_secret12345"],
            "request_id": "sk-abcdefghi",
        },
        status="completed",
        created_at_unix_ms=100,
        updated_at_unix_ms=90,
    )
    duplicate_metric = SimpleNamespace(name="bench.smoke.ttft_ms", value=12.5, unit="ms")

    record = build_serving_benchmark_run_record(
        job=job,
        results=(SimpleNamespace(metrics=(duplicate_metric, duplicate_metric)),),
        artifact_root=tmp_path / "root",
        artifact_paths={"external": tmp_path / "outside.json"},
    )

    assert record["duration_ms"] == 0
    assert record["command"]["display"] == "melix bench run --repo-id mlx-community/model --suite smoke"
    assert record["parameters"]["notes"] == ["safe", "[REDACTED]"]
    assert record["parameters"]["request_id"] == "[REDACTED]"
    assert record["artifacts"] == [
        {
            "kind": "external",
            "path": str(tmp_path / "outside.json"),
            "relative_path": "",
        }
    ]
    assert record["metrics"] == [{"name": "bench.smoke.ttft_ms", "value": 12.5, "unit": "ms"}]
    assert record["resources"]["peak_memory_bytes"] is None
    assert record["known_gaps"] == [
        "Apple Silicon telemetry artifact was not present for this run.",
        "Sensitive command or request values were redacted from the persisted run record.",
    ]


def test_evaluation_run_record_keeps_explicit_zero_reproduction_options(
    tmp_path: Path,
) -> None:
    job = SimpleNamespace(
        job_id="eval-zero",
        model_id="melix-dev-text",
        task_kind="text-generation",
        source_repo="",
        suite_id="mmlu",
        dataset_id="mmlu-dev",
        sample_size=0,
        scoring_mode="exact_match",
        few_shot=0,
        seed=0,
        code_exec_policy="disabled",
        parameters={},
        status="completed",
        created_at_unix_ms=100,
        updated_at_unix_ms=120,
    )
    result = SimpleNamespace(
        metrics=(),
        primary_score_name="exact_match",
        primary_score_value=0.0,
        scored_sample_count=0,
        failure_count=0,
        duration_seconds=0.0,
    )

    record = build_evaluation_run_record(
        job=job,
        result=result,
        artifact_root=tmp_path,
        artifact_paths={"telemetry_jsonl": tmp_path / "telemetry.jsonl"},
    )

    assert record["command"]["display"] == (
        "melix eval run --model-id melix-dev-text --suite mmlu "
        "--dataset-id mmlu-dev --sample-size 0 --scoring-mode exact_match "
        "--few-shot 0 --seed 0 --code-exec-policy disabled"
    )


def test_run_record_helper_fallbacks(monkeypatch) -> None:
    assert run_records._split_parameter_list(("1024", "", "2048")) == ["1024", "2048"]
    assert run_records._split_parameter_list("cold, warm,,") == ["cold", "warm"]
    assert run_records._matrix_values_from_rows((), "unknown") == []
    assert run_records._int_or_none("not-a-number") is None
    assert run_records._float_or_none("not-a-number") is None

    def fail_run(*args: object, **kwargs: object) -> object:
        raise RuntimeError("subprocess unavailable")

    monkeypatch.setattr(run_records.subprocess, "run", fail_run)
    monkeypatch.setattr(platform, "processor", lambda: "fallback-processor")
    run_records._apple_processor_name.cache_clear()
    run_records._melix_identity.cache_clear()

    assert run_records._apple_processor_name() == "fallback-processor"
    assert run_records._git_output(Path("/tmp"), "rev-parse", "HEAD") == ""
    assert run_records._git_dirty(Path("/tmp")) is False


def test_repo_root_falls_back_to_project_marker_when_git_is_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    nested = tmp_path / "services" / "mlx-worker-python" / "worker"
    nested.mkdir(parents=True)
    (tmp_path / ".git").mkdir()

    def fail_run(*args: object, **kwargs: object) -> object:
        raise RuntimeError("subprocess unavailable")

    monkeypatch.setattr(run_records.subprocess, "run", fail_run)

    assert run_records._repo_root(start=nested) == tmp_path
