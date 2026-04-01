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


def test_build_submission_payload_includes_device_and_results(tmp_path: Path) -> None:
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

    assert payload.device["chip"] == "Apple M2"
    assert len(payload.benchmark_jobs) == 1
    assert payload.benchmark_jobs[0]["job_id"] == "bench-1"
    assert len(payload.benchmark_results) == 1
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
