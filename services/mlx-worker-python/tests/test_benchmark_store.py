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
from telemetry_fixtures import fixture_telemetry_collector


class _CountingRow:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls = 0

    def to_dict(self) -> dict[str, object]:
        self.calls += 1
        return dict(self.payload)


def test_persist_serving_benchmark_writes_expected_artifact_names_and_payloads(
    tmp_path: Path,
) -> None:
    store = BenchmarkStore(telemetry_collector=fixture_telemetry_collector())
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
        model_memory_summary={
            "runtime_model_handle": "melix-dev-text::1",
            "runtime_model_id": "melix-dev-text",
            "runtime_kind": "text",
            "runtime_name": "fast-benchmark",
            "loaded_model_estimated_resident_bytes": 4096,
            "runtime_stats_model_resident_bytes": 4096,
            "runtime_stats_resident_bytes": 4096,
            "load_triggered_by_run": True,
            "load_rss_before_bytes": 100_000_000,
            "load_rss_after_bytes": 120_000_000,
            "load_rss_delta_bytes": 20_000_000,
        },
        context_rows=(
            {
                "job_id": "bench-123",
                "suite": "smoke",
                "context_length": 16,
                "generation_length": 8,
                "batch_size": 1,
                "dataset_materialize_ms": 1.0,
                "prompt_render_ms": 2.0,
                "warmup_ms": 3.0,
                "prefill_ms": 4.0,
                "decode_ms": 5.0,
                "cache_hit": True,
            },
        ),
    )

    assert persisted["job"] == jobs_root / "bench-job.json"
    assert persisted["smoke"] == jobs_root / "bench-result-smoke.json"
    assert persisted["latency"] == jobs_root / "bench-result-latency.json"
    assert persisted["context_rows_jsonl"] == jobs_root / "bench-context-rows.jsonl"
    assert persisted["telemetry_jsonl"] == jobs_root / "telemetry-samples.jsonl"
    assert persisted["evidence"] == jobs_root / "run-evidence.json"
    assert persisted["run_record"] == jobs_root / "run-record.json"
    assert json.loads(persisted["job"].read_text(encoding="utf-8")) == job.to_dict()
    expected_results = {result.suite: result.to_dict() for result in results}

    assert json.loads(persisted["smoke"].read_text(encoding="utf-8")) == expected_results["smoke"]
    assert json.loads(persisted["latency"].read_text(encoding="utf-8")) == expected_results["latency"]
    evidence = json.loads(persisted["evidence"].read_text(encoding="utf-8"))
    assert evidence["schema_version"] == "melix.run_evidence.v1"
    assert evidence["run_id"] == "bench-123"
    assert evidence["run_kind"] == "serving_benchmark"
    assert evidence["target_model_id"] == "melix-dev-text"
    phases = [probe["phase"] for probe in evidence["probe_timeline"]]
    assert phases[:4] == ["worker_dispatch", "runtime_prepare", "adapter_load", "cache_lookup"]
    assert "prefill" in phases
    assert "decode" in phases
    assert "hardware_sample" in phases
    assert "power_sample" in phases
    assert phases[-1] == "artifact_write"
    assert evidence["telemetry_summary"]["collector_status"] == "collected"
    assert evidence["telemetry_summary"]["time_series_path"] == "telemetry-samples.jsonl"
    assert evidence["telemetry_summary"]["average_system_power_w"] == 15.0
    assert evidence["telemetry_summary"]["process_attribution"]["primary_runtime_process"]["pid"] == 102
    assert evidence["model_memory_summary"]["runtime_model_handle"] == "melix-dev-text::1"
    assert evidence["model_memory_summary"]["loaded_model_estimated_resident_bytes"] == 4096
    assert evidence["model_memory_summary"]["runtime_stats_model_resident_bytes"] == 4096
    assert evidence["model_memory_summary"]["load_rss_delta_bytes"] == 20_000_000
    run_record = json.loads(persisted["run_record"].read_text(encoding="utf-8"))
    assert run_record["schema_version"] == "melix.run_record.v1"
    assert run_record["run_id"] == "bench-123"
    assert run_record["run_kind"] == "benchmark"
    assert run_record["command"]["display"].startswith("melix bench run --model-id melix-dev-text")
    assert {artifact["kind"] for artifact in run_record["artifacts"]} >= {
        "evidence",
        "run_record",
        "telemetry_jsonl",
    }
    assert run_record["probes"][0]["phase"] == "run_record_write"


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
    assert persisted["run_record"] == jobs_root / "run-record.json"
    assert json.loads(persisted["job"].read_text(encoding="utf-8")) == job.to_dict()
    assert [
        json.loads(line)
        for line in persisted["summary_jsonl"].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ] == [summary_rows[0].to_dict()]
    assert persisted["summary_jsonl"].read_text(encoding="utf-8").endswith("\n")
    assert [
        json.loads(line)
        for line in persisted["requests_jsonl"].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ] == [request_rows[0].to_dict()]
    assert persisted["requests_jsonl"].read_text(encoding="utf-8").endswith("\n")
    assert "job_id,task_kind,source_repo,model_id,suite_id,context_length" in persisted["summary_csv"].read_text(
        encoding="utf-8"
    )
    assert "job_id,cell_id,task_kind,suite_id,context_length,generation_length" in persisted["requests_csv"].read_text(
        encoding="utf-8"
    )
    run_record = json.loads(persisted["run_record"].read_text(encoding="utf-8"))
    assert run_record["schema_version"] == "melix.run_record.v1"
    assert run_record["run_kind"] == "benchmark_matrix"
    assert run_record["resources"]["peak_memory_bytes"] == 2_147_483_648
    assert run_record["metrics"][0]["name"] == "benchmark_matrix.decode_tokens_per_second_mean"
    assert run_record["known_gaps"] == ["Apple Silicon telemetry artifact was not present for this run."]
    assert run_record["probes"][0]["phase"] == "run_record_write"


def test_persist_benchmark_matrix_serializes_each_row_once_per_persist(tmp_path: Path) -> None:
    store = BenchmarkStore()
    jobs_root = tmp_path / "bench" / "matrix-runs" / "bench-matrix-counts"
    job = build_benchmark_matrix_job(
        job_id="bench-matrix-counts",
        model_id="melix-dev-text",
        task_kind="text-generation",
        source_repo="HuggingFaceH4/ultrachat_200k",
        suite_ids=("smoke",),
        status="completed",
        output_dir=str(jobs_root),
    )
    summary_row = _CountingRow(
        {
            "job_id": "bench-matrix-counts",
            "task_kind": "text-generation",
            "source_repo": "HuggingFaceH4/ultrachat_200k",
            "model_id": "melix-dev-text",
            "suite_id": "smoke",
            "context_length": 1024,
            "generation_length": 128,
            "batch_size": 2,
            "cache_profile": "cold",
            "reasoning_mode": "enabled",
            "structured_output_mode": "plain_text",
            "concurrency_level": 1,
            "repeats": 3,
            "requests": 24,
            "duration_seconds": 0,
            "ttft_mean_ms": 24.45,
            "ttft_std_ms": 1.2,
            "request_latency_mean_ms": 88.4,
            "request_latency_std_ms": 3.1,
            "prefill_tokens_per_second_mean": 1400.0,
            "decode_tokens_per_second_mean": 58.2,
            "throughput_requests_per_second": 3.8,
            "throughput_tokens_per_second": 221.5,
            "success_rate": 1.0,
            "peak_memory_bytes_max": 2_147_483_648,
            "queue_wait_mean_ms": 5.1,
            "queue_wait_p95_ms": 9.2,
            "created_at_unix_ms": 101,
        }
    )
    request_row = _CountingRow(
        {
            "job_id": "bench-matrix-counts",
            "cell_id": "cell-1",
            "task_kind": "text-generation",
            "suite_id": "smoke",
            "context_length": 1024,
            "generation_length": 128,
            "batch_size": 2,
            "cache_profile": "cold",
            "reasoning_mode": "enabled",
            "structured_output_mode": "plain_text",
            "concurrency_level": 1,
            "repeat_index": 0,
            "request_index": 0,
            "ttft_ms": 24.45,
            "request_latency_ms": 88.4,
            "prefill_tokens_per_second": 1400.0,
            "decode_tokens_per_second": 58.2,
            "queue_wait_ms": 5.1,
            "peak_memory_bytes": 2_147_483_648,
            "status": "completed",
            "error_code": "",
            "created_at_unix_ms": 101,
        }
    )

    store.persist_benchmark_matrix(
        jobs_root=jobs_root,
        job=job,
        summary_rows=(summary_row,),
        request_rows=(request_row,),
    )

    assert summary_row.calls == 1
    assert request_row.calls == 1


def test_persist_benchmark_matrix_preserves_empty_jsonl_artifacts(tmp_path: Path) -> None:
    store = BenchmarkStore()
    jobs_root = tmp_path / "bench" / "matrix-runs" / "bench-matrix-empty"
    job = build_benchmark_matrix_job(
        job_id="bench-matrix-empty",
        model_id="melix-dev-text",
        task_kind="text-generation",
        source_repo="HuggingFaceH4/ultrachat_200k",
        suite_ids=("smoke",),
        status="completed",
        output_dir=str(jobs_root),
    )

    persisted = store.persist_benchmark_matrix(
        jobs_root=jobs_root,
        job=job,
        summary_rows=(),
        request_rows=(),
    )

    assert persisted["summary_jsonl"].read_text(encoding="utf-8") == ""
    assert persisted["requests_jsonl"].read_text(encoding="utf-8") == ""
