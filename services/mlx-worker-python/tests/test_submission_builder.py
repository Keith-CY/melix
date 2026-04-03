from __future__ import annotations

import json
from pathlib import Path

from worker.productization.device_identity import DeviceIdentity
from worker.productization.submission_builder import build_submission_payload


def _write_bench_fixtures(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "bench-job.json").write_text(
        json.dumps({
            "schema_version": "melix.serving_benchmark_job.v1",
            "job_id": "bench-1",
            "model_id": "melix-dev-text",
            "suites": ["smoke"],
            "parameters": {},
            "status": "completed",
        }) + "\n"
    )
    (root / "bench-result-smoke.json").write_text(
        json.dumps({
            "schema_version": "melix.serving_benchmark_result.v1",
            "job_id": "bench-1",
            "suite": "smoke",
            "metrics": [
                {"name": "bench.smoke.ttft_ms", "value": 24.45, "unit": "ms"},
            ],
        }) + "\n"
    )


def _write_eval_fixtures(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "evaluation-job.json").write_text(
        json.dumps({
            "schema_version": "melix.evaluation_job.v1",
            "job_id": "eval-1",
            "model_id": "melix-dev-text",
            "task_kind": "text-generation",
            "source_repo": "HuggingFaceH4/ultrachat_200k",
            "suite_id": "mmlu",
            "dataset_id": "mmlu.dev.v1",
            "sample_size": 1,
            "status": "completed",
            "parameters": {},
            "output_dir": str(root),
            "created_at_unix_ms": 101,
            "updated_at_unix_ms": 202,
        }) + "\n"
    )
    (root / "evaluation-result.json").write_text(
        json.dumps({
            "schema_version": "melix.evaluation_result.v1",
            "job_id": "eval-1",
            "suite_id": "mmlu",
            "dataset_id": "mmlu.dev.v1",
            "sample_size": 1,
            "metrics": [{"name": "eval.mmlu.accuracy", "value": 1.0, "unit": "ratio"}],
            "report_path": str(root / "evaluation-result.json"),
        }) + "\n"
    )
    (root / "evaluation-samples.jsonl").write_text(
        json.dumps({
            "schema_version": "melix.evaluation_sample.v1",
            "job_id": "eval-1",
            "suite_id": "mmlu",
            "dataset_id": "mmlu.dev.v1",
            "sample_id": "1",
            "question": "2+2?",
            "expected": "4",
            "predicted": "4",
            "raw_response": "4",
            "correct": True,
            "time_s": 0.01,
            "parse_status": "parsed",
        }) + "\n"
    )


def test_build_submission_payload_includes_device_and_results(tmp_path: Path) -> None:
    _write_bench_fixtures(tmp_path)
    _write_eval_fixtures(tmp_path)
    device = DeviceIdentity(
        chip="Apple M2",
        memory_gb=16.0,
        os_version="15.0",
        os_build="24A335",
        hostname_hash="aabbccddeeff",
        melix_version="0.1.0",
    )

    payload = build_submission_payload(tmp_path, device)

    assert payload.device["chip"] == "Apple M2"
    assert len(payload.benchmark_jobs) == 1
    assert payload.benchmark_jobs[0]["job_id"] == "bench-1"
    assert len(payload.benchmark_results) == 1
    assert len(payload.evaluation_jobs) == 1
    assert len(payload.evaluation_results) == 1
    assert len(payload.evaluation_samples) == 1
    assert payload.submitted_at_unix_ms > 0


def test_submission_payload_to_dict_has_stable_schema_version(tmp_path: Path) -> None:
    _write_bench_fixtures(tmp_path)
    device = DeviceIdentity(
        chip="Apple M2",
        memory_gb=16.0,
        os_version="15.0",
        os_build="24A335",
        hostname_hash="aabbccddeeff",
        melix_version="0.1.0",
    )

    payload = build_submission_payload(tmp_path, device)
    result = payload.to_dict()

    assert result["schema_version"] == "melix.submission.v1"
    assert isinstance(result["device"], dict)
    assert isinstance(result["benchmark_jobs"], list)
    assert isinstance(result["evaluation_samples"], list)
