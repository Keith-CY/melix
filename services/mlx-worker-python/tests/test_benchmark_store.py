from __future__ import annotations

import json
from pathlib import Path

from worker.productization.benchmark_schemas import (
    build_serving_benchmark_job,
    build_serving_benchmark_results,
)
from worker.productization.benchmark_store import BenchmarkStore


def test_persist_serving_benchmark_writes_expected_artifact_names_and_payloads(
    tmp_path: Path,
) -> None:
    store = BenchmarkStore()
    jobs_root = tmp_path / "bench"
    job = build_serving_benchmark_job(
        job_id="bench-123",
        model_id="melix-dev-text",
        suites=("smoke", "latency"),
        parameters={},
        status="completed",
        output_dir=str(jobs_root),
    )
    results = build_serving_benchmark_results(
        job_id="bench-123",
        metrics={
            "bench.smoke.ttft_ms": 24.45,
            "bench.latency.p95_ms": 44.72,
        },
        units={
            "bench.smoke.ttft_ms": "ms",
            "bench.latency.p95_ms": "ms",
        },
        report_path=str(jobs_root / "bench-report.md"),
        report_markdown="# Melix Bench\n",
    )

    persisted = store.persist_serving_benchmark(
        jobs_root=jobs_root,
        job=job,
        results=results,
    )

    assert persisted["job"] == jobs_root / "bench-job.json"
    assert persisted["smoke"] == jobs_root / "bench-result-smoke.json"
    assert persisted["latency"] == jobs_root / "bench-result-latency.json"
    assert json.loads(persisted["job"].read_text(encoding="utf-8")) == job.to_dict()
    expected_results = {result.suite: result.to_dict() for result in results}

    assert json.loads(persisted["smoke"].read_text(encoding="utf-8")) == expected_results["smoke"]
    assert json.loads(persisted["latency"].read_text(encoding="utf-8")) == expected_results["latency"]
