from __future__ import annotations

import json
from pathlib import Path

from worker.productization.benchmark_schemas import (
    build_benchmark_matrix_job,
    build_benchmark_matrix_request_row,
    build_benchmark_matrix_summary_row,
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


def test_persist_benchmark_matrix_writes_job_summary_request_and_csv_artifacts(
    tmp_path: Path,
) -> None:
    store = BenchmarkStore()
    jobs_root = tmp_path / "bench" / "matrix-runs" / "bench-matrix-1"
    job = build_benchmark_matrix_job(
        job_id="bench-matrix-1",
        model_id="melix-dev-text",
        task_kind="text-generation",
        source_repo="HuggingFaceH4/ultrachat_200k",
        suite_ids=("smoke",),
        status="completed",
        output_dir=str(jobs_root),
    )
    summary_rows = (
        build_benchmark_matrix_summary_row(
            job_id="bench-matrix-1",
            task_kind="text-generation",
            source_repo="HuggingFaceH4/ultrachat_200k",
            model_id="melix-dev-text",
            suite_id="smoke",
            context_length=1024,
            generation_length=128,
            batch_size=2,
            cache_profile="cold",
            reasoning_mode="enabled",
            structured_output_mode="plain_text",
            concurrency_level=1,
            repeats=3,
            requests=24,
            duration_seconds=0,
            ttft_mean_ms=24.45,
            ttft_std_ms=1.2,
            request_latency_mean_ms=88.4,
            request_latency_std_ms=3.1,
            prefill_tokens_per_second_mean=1400.0,
            decode_tokens_per_second_mean=58.2,
            throughput_requests_per_second=3.8,
            throughput_tokens_per_second=221.5,
            success_rate=1.0,
            peak_memory_bytes_max=2_147_483_648,
            queue_wait_mean_ms=5.1,
            queue_wait_p95_ms=9.2,
            created_at_unix_ms=101,
        ),
    )
    request_rows = (
        build_benchmark_matrix_request_row(
            job_id="bench-matrix-1",
            cell_id="cell-1",
            task_kind="text-generation",
            suite_id="smoke",
            context_length=1024,
            generation_length=128,
            batch_size=2,
            cache_profile="cold",
            reasoning_mode="enabled",
            structured_output_mode="plain_text",
            concurrency_level=1,
            repeat_index=0,
            request_index=0,
            ttft_ms=24.45,
            request_latency_ms=88.4,
            prefill_tokens_per_second=1400.0,
            decode_tokens_per_second=58.2,
            queue_wait_ms=5.1,
            peak_memory_bytes=2_147_483_648,
            status="completed",
            error_code="",
            created_at_unix_ms=101,
        ),
    )

    persisted = store.persist_benchmark_matrix(
        jobs_root=jobs_root,
        job=job,
        summary_rows=summary_rows,
        request_rows=request_rows,
    )

    assert persisted["job"] == jobs_root / "bench-matrix-job.json"
    assert persisted["summary_jsonl"] == jobs_root / "bench-matrix-summary.jsonl"
    assert persisted["summary_csv"] == jobs_root / "bench-matrix-summary.csv"
    assert persisted["requests_jsonl"] == jobs_root / "bench-matrix-requests.jsonl"
    assert persisted["requests_csv"] == jobs_root / "bench-matrix-requests.csv"
    assert json.loads(persisted["job"].read_text(encoding="utf-8")) == job.to_dict()
    assert [
        json.loads(line)
        for line in persisted["summary_jsonl"].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ] == [summary_rows[0].to_dict()]
    assert [
        json.loads(line)
        for line in persisted["requests_jsonl"].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ] == [request_rows[0].to_dict()]
    assert "job_id,task_kind,source_repo,model_id,suite_id,context_length" in persisted["summary_csv"].read_text(
        encoding="utf-8"
    )
    assert "job_id,cell_id,task_kind,suite_id,context_length,generation_length" in persisted["requests_csv"].read_text(
        encoding="utf-8"
    )
