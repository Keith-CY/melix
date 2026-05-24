from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from worker.productization.benchmark_export import (
    build_benchmark_context_csv,
    build_benchmark_requests_csv,
    collect_benchmark_artifacts,
)
from worker.productization import benchmark_store as benchmark_store_module
from worker.productization.benchmark_schemas import (
    build_benchmark_matrix_job,
    build_benchmark_matrix_request_row,
    build_benchmark_matrix_summary_row,
    build_serving_benchmark_job,
    build_serving_benchmark_request_row,
    build_serving_benchmark_results,
)
from worker.productization.benchmark_store import BenchmarkStore
from worker.productization.probe_policy import ProbeMode, ProbePolicy
from telemetry_fixtures import fixture_telemetry_collector, guard_production_safe_probe_paths


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


def test_persist_serving_benchmark_writes_request_phase_rows_and_exports(
    tmp_path: Path,
) -> None:
    store = BenchmarkStore(telemetry_collector=fixture_telemetry_collector())
    jobs_root = tmp_path / "bench"
    job = build_serving_benchmark_job(
        job_id="bench-agentic",
        model_id="melix-dev-text",
        task_kind="text-generation",
        source_repo="local",
        suites=("agentic_visit",),
        parameters={},
        status="completed",
        output_dir=str(jobs_root),
    )
    results = build_serving_benchmark_results(
        job_id="bench-agentic",
        metrics={"bench.agentic_visit.ttft_ms": 24.45},
        units={"bench.agentic_visit.ttft_ms": "ms"},
        report_path=str(jobs_root / "bench-report.md"),
        report_markdown="# Melix Bench\n",
    )
    request_rows = (
        build_serving_benchmark_request_row(
            job_id="bench-agentic",
            model_id="melix-dev-text",
            task_kind="text-generation",
            source_repo="local",
            suite="agentic_visit",
            context_length=64,
            generation_length=16,
            batch_size=1,
            repeat_index=0,
            request_index=0,
            phase="tool_turn",
            phase_index=0,
            status="completed",
            duration_ms=5.5,
            tool_call_id="visit-1",
            tool_name="visit",
            tool_arguments={"url": "fixture://page"},
            tool_observation={"status": "completed", "payload": {"text": "Visited."}},
            agentic_tool_metrics={
                "agentic_tool.call_count": 1.0,
                "agentic_tool.latency_ms": 5.5,
                "agentic_tool.observation_count": 1.0,
                "agentic_tool.observation_emitted_bytes": 64.0,
            },
            created_at_unix_ms=101,
        ),
        build_serving_benchmark_request_row(
            job_id="bench-agentic",
            model_id="melix-dev-text",
            task_kind="text-generation",
            source_repo="local",
            suite="agentic_visit",
            context_length=64,
            generation_length=16,
            batch_size=1,
            repeat_index=0,
            request_index=0,
            phase="final_answer",
            phase_index=1,
            status="completed",
            duration_ms=42.8,
            request_latency_ms=42.8,
            tokens_out=16,
            tool_call_count=1,
            tool_latency_ms=5.5,
            observation_bytes=64,
            turn_count=2,
            created_at_unix_ms=102,
        ),
    )

    persisted = store.persist_serving_benchmark(
        jobs_root=jobs_root,
        job=job,
        results=results,
        request_rows=request_rows,
    )

    assert persisted["request_rows_jsonl"] == jobs_root / "bench-request-rows.jsonl"
    assert persisted["request_rows_csv"] == jobs_root / "bench-request-rows.csv"
    jsonl_rows = [
        json.loads(line)
        for line in persisted["request_rows_jsonl"].read_text(encoding="utf-8").splitlines()
    ]
    assert [row["phase"] for row in jsonl_rows] == ["tool_turn", "final_answer"]
    assert jsonl_rows[0]["tool_name"] == "visit"
    assert jsonl_rows[1]["tool_call_id"] == ""

    export_bundle = collect_benchmark_artifacts(jobs_root)
    assert [row["phase"] for row in export_bundle["benchmark_request_rows"]] == [
        "tool_turn",
        "final_answer",
    ]
    request_csv_rows = list(csv.DictReader(build_benchmark_requests_csv(export_bundle).splitlines()))
    assert request_csv_rows[0]["tool_call_id"] == "visit-1"
    assert request_csv_rows[0]["compare_target_kind"] == "base"
    assert request_csv_rows[0]["base_model_id"] == "melix-dev-text"
    assert request_csv_rows[1]["phase"] == "final_answer"


def test_persist_serving_benchmark_request_rows_attach_adapter_identity(
    tmp_path: Path,
) -> None:
    store = BenchmarkStore(telemetry_collector=fixture_telemetry_collector())
    jobs_root = tmp_path / "bench"
    job = build_serving_benchmark_job(
        job_id="bench-adapter",
        model_id="melix-dev-text-lora-deadbeef",
        task_kind="text-generation",
        source_repo="local",
        suites=("agentic_visit",),
        parameters={
            "melix.derived_from_model_id": "melix-dev-text",
            "melix.adapter_manifest_path": "/tmp/melix/train_lora.adapter.json",
            "melix.adapter_set_hash": "deadbeefcafebabe",
            "melix.activation_mode": "adapter_backed_runtime",
        },
        status="completed",
        output_dir=str(jobs_root),
    )
    results = build_serving_benchmark_results(
        job_id="bench-adapter",
        metrics={"bench.agentic_visit.ttft_ms": 24.45},
        units={"bench.agentic_visit.ttft_ms": "ms"},
        report_path=str(jobs_root / "bench-report.md"),
        report_markdown="# Melix Bench\n",
    )
    request_row = build_serving_benchmark_request_row(
        job_id="bench-adapter",
        model_id="melix-dev-text-lora-deadbeef",
        task_kind="text-generation",
        source_repo="local",
        suite="agentic_visit",
        context_length=64,
        generation_length=16,
        batch_size=1,
        repeat_index=0,
        request_index=0,
        phase="tool_turn",
        phase_index=0,
        status="completed",
        tool_call_count=1,
        tool_latency_ms=5.5,
        created_at_unix_ms=101,
    )

    persisted = store.persist_serving_benchmark(
        jobs_root=jobs_root,
        job=job,
        results=results,
        request_rows=(request_row,),
    )

    jsonl_row = json.loads(persisted["request_rows_jsonl"].read_text(encoding="utf-8").splitlines()[0])
    assert jsonl_row["compare_target_kind"] == "adapter"
    assert jsonl_row["base_model_id"] == "melix-dev-text"
    assert jsonl_row["adapter_manifest_path"] == "/tmp/melix/train_lora.adapter.json"
    assert jsonl_row["adapter_set_hash"] == "deadbeefcafebabe"
    assert jsonl_row["adapter_activation_mode"] == "adapter_backed_runtime"


def test_persist_serving_benchmark_writes_repeat_group_artifact_from_existing_rows(
    tmp_path: Path,
) -> None:
    store = BenchmarkStore(telemetry_collector=fixture_telemetry_collector())
    jobs_root = tmp_path / "bench"
    job = build_serving_benchmark_job(
        job_id="bench-repeat",
        model_id="melix-dev-text",
        task_kind="text-generation",
        source_repo="local",
        suites=("smoke",),
        context_lengths=(64,),
        generation_length=16,
        batch_sizes=(1,),
        repeats=3,
        parameters={},
        status="completed",
        output_dir=str(jobs_root),
    )
    results = build_serving_benchmark_results(
        job_id="bench-repeat",
        metrics={"bench.smoke.tokens_per_second": 102.0},
        units={"bench.smoke.tokens_per_second": "tok/s"},
        report_path=str(jobs_root / "bench-report.md"),
        report_markdown="# Melix Bench\n",
    )
    context_rows = tuple(
        {
            "schema_version": "melix.serving_benchmark_context_row.v1",
            "job_id": "bench-repeat",
            "model_id": "melix-dev-text",
            "task_kind": "text-generation",
            "source_repo": "local",
            "suite": "smoke",
            "context_length": 64,
            "generation_length": 16,
            "batch_size": 1,
            "repeat_index": repeat_index,
            "prefill_tokens_per_second": 1000.0 + repeat_index,
            "decode_tokens_per_second": decode_tps,
            "ttft_ms": ttft_ms,
            "request_latency_ms": latency_ms,
            "peak_memory_bytes": memory_bytes,
            "speedup_vs_batch_1": 1.0,
            "cache_profile": "cold",
            "reasoning_mode": "",
            "structured_output_mode": "",
            "energy_joules": energy_joules,
        }
        for repeat_index, decode_tps, ttft_ms, latency_ms, memory_bytes, energy_joules in (
            (0, 100.0, 10.0, 40.0, 2048.0, 4.0),
            (1, 102.0, 12.0, 42.0, 2080.0, 4.2),
            (2, 104.0, 14.0, 44.0, 2112.0, 4.4),
        )
    )

    persisted = store.persist_serving_benchmark(
        jobs_root=jobs_root,
        job=job,
        results=results,
        context_rows=context_rows,
    )

    assert persisted["repeat_groups_jsonl"] == jobs_root / "bench-repeat-groups.jsonl"
    rows = [
        json.loads(line)
        for line in persisted["repeat_groups_jsonl"].read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 1
    row = rows[0]
    assert row["schema_version"] == "melix.serving_benchmark_repeat_group.v1"
    assert row["group_id"] == "bench-repeat:context:smoke:64:16:1:cold:::"
    assert row["source_row_kind"] == "context"
    assert row["repetition_index"] == [0, 1, 2]
    assert row["sample_count"] == 3
    assert row["seed_strategy"] == "runner_repeat_index"
    assert row["throughput_mean"] == 102.0
    assert row["throughput_stdev"] == 2.0
    assert row["throughput_ci95_low"] == 99.7368
    assert row["throughput_ci95_high"] == 104.2632
    assert row["ttft_ms_mean"] == 12.0
    assert row["ttft_ms_stdev"] == 2.0
    assert row["ttft_ms_ci95_low"] == 9.7368
    assert row["ttft_ms_ci95_high"] == 14.2632
    assert row["peak_memory_bytes_mean"] == 2080.0
    assert row["peak_memory_bytes_stdev"] == 32.0
    assert row["energy_joules_mean"] == 4.2


def test_repeat_group_aggregates_unique_repetitions_not_case_rows() -> None:
    rows = BenchmarkStore._repeat_group_rows_from_benchmark_rows(
        context_rows=(
            {
                "schema_version": "melix.serving_benchmark_context_row.v1",
                "job_id": "bench-multi-case",
                "model_id": "melix-dev-text",
                "task_kind": "text-generation",
                "source_repo": "local",
                "suite": "smoke",
                "context_length": 64,
                "generation_length": 16,
                "batch_size": 1,
                "repeat_index": 0,
                "request_index": 0,
                "decode_tokens_per_second": 100.0,
                "ttft_ms": 10.0,
                "request_latency_ms": 40.0,
                "peak_memory_bytes": 2000.0,
                "cache_profile": "cold",
                "reasoning_mode": "",
                "structured_output_mode": "",
            },
            {
                "schema_version": "melix.serving_benchmark_context_row.v1",
                "job_id": "bench-multi-case",
                "model_id": "melix-dev-text",
                "task_kind": "text-generation",
                "source_repo": "local",
                "suite": "smoke",
                "context_length": 64,
                "generation_length": 16,
                "batch_size": 1,
                "repeat_index": 0,
                "request_index": 1,
                "decode_tokens_per_second": 120.0,
                "ttft_ms": 14.0,
                "request_latency_ms": 44.0,
                "peak_memory_bytes": 2200.0,
                "cache_profile": "cold",
                "reasoning_mode": "",
                "structured_output_mode": "",
            },
        ),
        batch_rows=(),
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["repetition_index"] == [0]
    assert row["sample_count"] == 1
    assert row["throughput_mean"] == 110.0
    assert row["throughput_stdev"] == 0.0
    assert row["throughput_ci95_low"] == 110.0
    assert row["throughput_ci95_high"] == 110.0
    assert "energy_joules_mean" not in row


def test_repeat_group_helpers_tolerate_sparse_rows_and_single_sample() -> None:
    rows = BenchmarkStore._repeat_group_rows_from_benchmark_rows(
        context_rows=(
            "not-a-row",  # type: ignore[arg-type]
            {"job_id": "bench-sparse"},
            {
                "schema_version": "melix.serving_benchmark_context_row.v1",
                "job_id": "bench-single",
                "model_id": "melix-dev-text",
                "task_kind": "text-generation",
                "source_repo": "local",
                "suite": "smoke",
                "context_length": "64",
                "generation_length": "bad-int",
                "batch_size": 1,
                "repeat_index": "bad-repeat",
                "decode_tokens_per_second": "not-a-float",
                "ttft_ms": 10.0,
                "request_latency_ms": 40.0,
                "peak_memory_bytes": 2048.0,
                "cache_profile": "cold",
                "reasoning_mode": "",
                "structured_output_mode": "",
            },
        ),
        batch_rows=(),
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["group_id"] == "bench-single:context:smoke:64:0:1:cold:::"
    assert row["repetition_index"] == [0]
    assert row["sample_count"] == 1
    assert row["throughput_mean"] == 0.0
    assert row["throughput_ci95_low"] == 0.0
    assert row["ttft_ms_mean"] == 10.0
    assert row["ttft_ms_stdev"] == 0.0
    assert row["ttft_ms_ci95_low"] == 10.0
    assert row["ttft_ms_ci95_high"] == 10.0


def test_persist_serving_benchmark_clears_stale_adapter_identity_for_base_rows(
    tmp_path: Path,
) -> None:
    store = BenchmarkStore(telemetry_collector=fixture_telemetry_collector())
    jobs_root = tmp_path / "bench"
    job = build_serving_benchmark_job(
        job_id="bench-base",
        model_id="melix-dev-text",
        task_kind="text-generation",
        source_repo="local",
        suites=("agentic_visit",),
        parameters={},
        status="completed",
        output_dir=str(jobs_root),
    )
    results = build_serving_benchmark_results(
        job_id="bench-base",
        metrics={"bench.agentic_visit.ttft_ms": 24.45},
        units={"bench.agentic_visit.ttft_ms": "ms"},
        report_path=str(jobs_root / "bench-report.md"),
        report_markdown="# Melix Bench\n",
    )
    request_row = build_serving_benchmark_request_row(
        job_id="bench-base",
        model_id="melix-dev-text",
        task_kind="text-generation",
        source_repo="local",
        suite="agentic_visit",
        context_length=64,
        generation_length=16,
        batch_size=1,
        repeat_index=0,
        request_index=0,
        phase="final_answer",
        phase_index=0,
        status="completed",
        compare_target_kind="adapter",
        base_model_id="melix-dev-text-base",
        adapter_manifest_path="/tmp/stale.adapter.json",
        adapter_set_hash="text-family-llama",
        adapter_activation_mode="stale",
    )

    persisted = store.persist_serving_benchmark(
        jobs_root=jobs_root,
        job=job,
        results=results,
        request_rows=(request_row,),
    )

    jsonl_row = json.loads(persisted["request_rows_jsonl"].read_text(encoding="utf-8").splitlines()[0])
    assert jsonl_row["compare_target_kind"] == "base"
    assert jsonl_row["base_model_id"] == "melix-dev-text"
    assert jsonl_row["adapter_manifest_path"] == ""
    assert jsonl_row["adapter_set_hash"] == ""
    assert jsonl_row["adapter_activation_mode"] == ""


def test_persist_serving_benchmark_derives_request_phase_rows_from_context_rows(
    tmp_path: Path,
) -> None:
    store = BenchmarkStore(telemetry_collector=fixture_telemetry_collector())
    jobs_root = tmp_path / "bench"
    job = build_serving_benchmark_job(
        job_id="bench-derived-agentic",
        model_id="melix-dev-text",
        task_kind="text-generation",
        source_repo="local",
        suites=("agentic_visit",),
        parameters={},
        status="completed",
        output_dir=str(jobs_root),
    )
    results = build_serving_benchmark_results(
        job_id="bench-derived-agentic",
        metrics={"bench.agentic_visit.ttft_ms": 24.45},
        units={"bench.agentic_visit.ttft_ms": "ms"},
        report_path=str(jobs_root / "bench-report.md"),
        report_markdown="# Melix Bench\n",
    )
    context_row = {
        "schema_version": "melix.serving_benchmark_context_row.v1",
        "job_id": "bench-derived-agentic",
        "model_id": "melix-dev-text",
        "task_kind": "text-generation",
        "source_repo": "local",
        "suite": "agentic_visit",
        "context_length": 64,
        "generation_length": 16,
        "batch_size": 1,
        "repeat_index": 0,
        "prefill_tokens_per_second": 1400.0,
        "decode_tokens_per_second": 58.2,
        "ttft_ms": 12.3,
        "request_latency_ms": 42.8,
        "peak_memory_bytes": 4096,
        "speedup_vs_batch_1": 1.0,
        "cache_profile": "cold",
        "reasoning_mode": "",
        "structured_output_mode": "",
        "dataset_materialize_ms": 2.0,
        "prompt_render_ms": 3.0,
        "warmup_ms": 4.0,
        "prefill_ms": 5.0,
        "decode_ms": 6.0,
        "tokens_in": 32,
        "tokens_out": 16,
        "first_token_index": 1,
        "cache_hit": True,
        "runtime_kind": "text",
        "agentic_tool_calls": [
            {"id": "visit-1", "name": "visit", "arguments": {"url": "fixture://page"}}
        ],
        "agentic_tool_observations": [
            {
                "status": "completed",
                "payload": {"text": "Visited."},
                "metrics": {"tool_observation.emitted_bytes": 64},
            }
        ],
        "agentic_tool_metrics": {
            "agentic_tool.call_count": 1.0,
            "agentic_tool.latency_ms": 5.5,
            "agentic_tool.observation_count": 1.0,
            "agentic_tool.observation_emitted_bytes": 64.0,
        },
        "trajectory_dataset_id": "opensearch-vl.dev",
        "trajectory_trace_digest": "abc123",
    }

    persisted = store.persist_serving_benchmark(
        jobs_root=jobs_root,
        job=job,
        results=results,
        context_rows=(context_row,),
    )

    request_rows = [
        json.loads(line)
        for line in persisted["request_rows_jsonl"].read_text(encoding="utf-8").splitlines()
    ]
    assert [row["phase"] for row in request_rows] == ["tool_turn", "final_answer"]
    assert request_rows[0]["phase_index"] == 0
    assert request_rows[0]["tool_call_id"] == "visit-1"
    assert request_rows[0]["tool_arguments_json"] == '{"url":"fixture://page"}'
    assert request_rows[0]["tool_observation_json"]
    assert request_rows[0]["observation_bytes"] == 64
    assert request_rows[0]["tool_latency_ms"] == 5.5
    assert request_rows[0]["trajectory_dataset_id"] == "opensearch-vl.dev"
    assert request_rows[0]["compare_target_kind"] == "base"
    assert request_rows[0]["base_model_id"] == "melix-dev-text"
    assert request_rows[1]["phase_index"] == 1
    assert request_rows[1]["request_latency_ms"] == 42.8
    assert request_rows[1]["tokens_out"] == 16
    assert request_rows[1]["tool_call_count"] == 1
    assert persisted["request_rows_csv"] == jobs_root / "bench-request-rows.csv"


def test_persist_serving_benchmark_request_row_derivation_skips_malformed_tool_turns(
    tmp_path: Path,
) -> None:
    store = BenchmarkStore(telemetry_collector=fixture_telemetry_collector())
    jobs_root = tmp_path / "bench"
    job = build_serving_benchmark_job(
        job_id="bench-malformed-agentic",
        model_id="melix-dev-text",
        task_kind="text-generation",
        source_repo="local",
        suites=("agentic_visit",),
        parameters={},
        status="completed",
        output_dir=str(jobs_root),
    )
    results = build_serving_benchmark_results(
        job_id="bench-malformed-agentic",
        metrics={"bench.agentic_visit.ttft_ms": 24.45},
        units={"bench.agentic_visit.ttft_ms": "ms"},
        report_path=str(jobs_root / "bench-report.md"),
        report_markdown="# Melix Bench\n",
    )

    persisted = store.persist_serving_benchmark(
        jobs_root=jobs_root,
        job=job,
        results=results,
        context_rows=(
            {
                "schema_version": "melix.serving_benchmark_context_row.v1",
                "job_id": "bench-malformed-agentic",
                "model_id": "melix-dev-text",
                "task_kind": "text-generation",
                "source_repo": "local",
                "suite": "agentic_visit",
                "context_length": 64,
                "generation_length": 16,
                "batch_size": 1,
                "repeat_index": 0,
                "ttft_ms": 1.0,
                "request_latency_ms": 2.0,
                "agentic_tool_calls": [
                    "malformed-call",
                    {"id": "visit-2", "name": "visit", "arguments": {"url": "fixture://page"}},
                ],
                "agentic_tool_observations": [
                    {"status": "completed"},
                    {
                        "status": "completed",
                        "metrics": {"tool_observation.emitted_bytes": "not-an-int"},
                    },
                ],
                "agentic_tool_metrics": {"agentic_tool.latency_ms": 12.0},
            },
        ),
    )

    request_rows = [
        json.loads(line)
        for line in persisted["request_rows_jsonl"].read_text(encoding="utf-8").splitlines()
    ]
    assert [row["phase"] for row in request_rows] == ["tool_turn", "final_answer"]
    assert request_rows[0]["phase_index"] == 0
    assert request_rows[0]["tool_call_id"] == "visit-2"
    assert request_rows[0]["observation_bytes"] == 0
    assert request_rows[1]["phase_index"] == 1


def test_serving_benchmark_request_row_derivation_ignores_invalid_context_values() -> None:
    assert benchmark_store_module._dict_float_mapping({"bad": "not-a-float"}) == {}
    assert benchmark_store_module._float_value("not-a-float") == 0.0
    assert BenchmarkStore._request_rows_from_context_rows(
        (
            "malformed-context",
            {
                "schema_version": "melix.serving_benchmark_context_row.v1",
                "job_id": "bench-invalid-values",
                "model_id": "melix-dev-text",
                "task_kind": "text-generation",
                "source_repo": "local",
                "suite": "agentic_visit",
                "context_length": "not-an-int",
                "generation_length": "also-not-an-int",
                "batch_size": 1,
                "repeat_index": 0,
                "ttft_ms": "not-a-float",
                "request_latency_ms": "not-a-float",
            },
        )
    )[0].to_dict()["request_latency_ms"] == 0.0


def test_persist_serving_benchmark_exports_trajectory_provenance_fields(
    tmp_path: Path,
) -> None:
    store = BenchmarkStore(telemetry_collector=fixture_telemetry_collector())
    jobs_root = tmp_path / "bench"
    snapshot_manifest = tmp_path / "snapshots" / "normalized_dataset" / "manifest.json"
    snapshot_manifest.parent.mkdir(parents=True)
    snapshot_manifest.write_text("{}\n", encoding="utf-8")
    provenance = {
        "trajectory_dataset_id": "opensearch-vl.dev",
        "trajectory_dataset_version": "2026-05-19",
        "trajectory_schema_version": "melix.agentic_tool_trace.v1",
        "trajectory_snapshot_manifest_path": str(snapshot_manifest),
        "trajectory_package_path": str(tmp_path / "packages" / "opensearch-vl.dev"),
        "trajectory_split": "train",
        "trajectory_trace_digest": "abc123",
        "trajectory_toolset_version": "melix.agentic_tools.builtin.v1",
        "trajectory_reward_policy_id": "reward-policy.v1",
        "trajectory_quality_metrics": {"agentic_trace_count": 1},
    }
    job = build_serving_benchmark_job(
        job_id="bench-trajectory",
        model_id="melix-dev-text",
        source_repo="local",
        suites=("agentic",),
        parameters={},
        status="completed",
        output_dir=str(jobs_root),
        trajectory_provenance=provenance,
    )
    results = build_serving_benchmark_results(
        job_id="bench-trajectory",
        metrics={"bench.agentic.ttft_ms": 24.45},
        units={"bench.agentic.ttft_ms": "ms"},
        report_path=str(jobs_root / "bench-report.md"),
        report_markdown="# Melix Bench\n",
    )
    context_row = {
        "job_id": "bench-trajectory",
        "model_id": "melix-dev-text",
        "task_kind": "text-generation",
        "source_repo": "local",
        "suite": "agentic",
        "context_length": 16,
        "generation_length": 8,
        "batch_size": 1,
        "repeat_index": 0,
        "prefill_tokens_per_second": 1.0,
        "decode_tokens_per_second": 1.0,
        "ttft_ms": 1.0,
        "request_latency_ms": 2.0,
        "peak_memory_bytes": 4096,
        "speedup_vs_batch_1": 1.0,
        "cache_profile": "cold",
        "reasoning_mode": "",
        "structured_output_mode": "",
        **provenance,
    }

    persisted = store.persist_serving_benchmark(
        jobs_root=jobs_root,
        job=job,
        results=results,
        context_rows=(context_row,),
    )

    context_jsonl = json.loads(persisted["context_rows_jsonl"].read_text(encoding="utf-8"))
    evidence = json.loads(persisted["evidence"].read_text(encoding="utf-8"))
    export_bundle = collect_benchmark_artifacts(jobs_root)
    context_csv = build_benchmark_context_csv(export_bundle)

    assert context_jsonl["trajectory_dataset_id"] == "opensearch-vl.dev"
    assert "trajectory_trace_digest" in context_csv.splitlines()[0]
    assert ",abc123," in context_csv
    assert evidence["domain_results"]["trajectory_provenance"]["trajectory_reward_policy_id"] == "reward-policy.v1"
    assert {
        artifact["kind"]
        for artifact in evidence["artifacts"]
    } >= {"trajectory_snapshot_manifest", "trajectory_package"}


def test_persist_serving_benchmark_defaults_to_no_op_telemetry(tmp_path: Path) -> None:
    store = BenchmarkStore(probe_policy=ProbePolicy(mode=ProbeMode.MINIMAL))
    jobs_root = tmp_path / "bench"
    job = build_serving_benchmark_job(
        job_id="bench-no-op",
        model_id="melix-dev-text",
        suites=("smoke",),
        parameters={},
        status="completed",
        output_dir=str(jobs_root),
    )
    results = build_serving_benchmark_results(
        job_id="bench-no-op",
        metrics={},
        units={},
        report_path=str(jobs_root / "bench-report.md"),
        report_markdown="# Melix Bench\n",
    )

    persisted = store.persist_serving_benchmark(
        jobs_root=jobs_root,
        job=job,
        results=results,
    )

    evidence = json.loads(persisted["evidence"].read_text(encoding="utf-8"))
    assert persisted["telemetry_jsonl"] == jobs_root / "telemetry-samples.jsonl"
    assert evidence["telemetry_summary"]["collector_status"] == "disabled"
    assert evidence["telemetry_summary"]["sample_count"] == 0
    assert evidence["telemetry_summary"]["time_series_path"] == "telemetry-samples.jsonl"
    telemetry_rows = [
        json.loads(line)
        for line in persisted["telemetry_jsonl"].read_text(encoding="utf-8").splitlines()
    ]
    assert telemetry_rows[0]["sample_kind"] == "telemetry_disabled"
    assert telemetry_rows[0]["reason"] == "probe_mode_minimal"
    telemetry_probes = [
        probe for probe in evidence["probe_timeline"] if probe["component"] == "telemetry"
    ]
    assert {probe["status"] for probe in telemetry_probes} == {"skipped"}


def test_benchmark_store_evidence_policy_uses_full_collector() -> None:
    store = BenchmarkStore(probe_policy=ProbePolicy(mode=ProbeMode.EVIDENCE))

    assert type(store._telemetry_collector).__name__ == "AppleSiliconTelemetryCollector"


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
            tool_call_count=2,
            tool_latency_ms=12.5,
            observation_bytes=96,
            fatal_rate=0.5,
            turn_count=4,
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
            tool_call_count=1,
            tool_latency_ms=6.25,
            observation_bytes=48,
            fatal_rate=0.0,
            turn_count=2,
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
    assert "tool_call_count,tool_latency_ms,observation_bytes,fatal_rate,turn_count" in persisted[
        "summary_csv"
    ].read_text(encoding="utf-8")
    assert ",2,12.5,96,0.5,4," in persisted["summary_csv"].read_text(encoding="utf-8")
    assert ",1,6.25,48,0.0,2," in persisted["requests_csv"].read_text(encoding="utf-8")
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


def test_attach_matrix_tool_turn_summary_fields_ignores_non_schema_request_rows() -> None:
    summary_row = build_benchmark_matrix_summary_row(
        job_id="bench-matrix-non-schema",
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
        repeats=1,
        requests=1,
        duration_seconds=0,
        ttft_mean_ms=24.45,
        ttft_std_ms=0.0,
        request_latency_mean_ms=88.4,
        request_latency_std_ms=0.0,
        prefill_tokens_per_second_mean=1400.0,
        decode_tokens_per_second_mean=58.2,
        throughput_requests_per_second=3.8,
        throughput_tokens_per_second=221.5,
        success_rate=1.0,
        peak_memory_bytes_max=2_147_483_648,
        queue_wait_mean_ms=5.1,
        queue_wait_p95_ms=9.2,
    )
    request_row = _CountingRow(
        {
            "job_id": "bench-matrix-non-schema",
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
            "tool_call_count": 1,
        }
    )

    hydrated = BenchmarkStore._attach_matrix_tool_turn_summary_fields(
        summary_rows=(summary_row,),
        request_rows=(request_row,),
    )

    assert hydrated == (summary_row,)
    assert request_row.calls == 0


def test_attach_matrix_tool_turn_summary_fields_hydrates_matching_summary_rows() -> None:
    summary_row = build_benchmark_matrix_summary_row(
        job_id="bench-matrix-hydrate",
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
        repeats=2,
        requests=2,
        duration_seconds=0,
        ttft_mean_ms=24.45,
        ttft_std_ms=0.0,
        request_latency_mean_ms=88.4,
        request_latency_std_ms=0.0,
        prefill_tokens_per_second_mean=1400.0,
        decode_tokens_per_second_mean=58.2,
        throughput_requests_per_second=3.8,
        throughput_tokens_per_second=221.5,
        success_rate=1.0,
        peak_memory_bytes_max=2_147_483_648,
        queue_wait_mean_ms=5.1,
        queue_wait_p95_ms=9.2,
    )
    first_request_row = build_benchmark_matrix_request_row(
        job_id="bench-matrix-hydrate",
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
        tool_call_count=1,
        tool_latency_ms=6.25,
        observation_bytes=48,
        fatal_rate=0.0,
        turn_count=2,
    )
    second_request_row = build_benchmark_matrix_request_row(
        job_id="bench-matrix-hydrate",
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
        request_index=1,
        ttft_ms=25.0,
        request_latency_ms=90.0,
        prefill_tokens_per_second=1300.0,
        decode_tokens_per_second=55.0,
        queue_wait_ms=5.4,
        peak_memory_bytes=2_147_483_648,
        status="completed",
        error_code="",
        created_at_unix_ms=102,
        tool_call_count=2,
        tool_latency_ms=3.75,
        observation_bytes=12,
        fatal_rate=1.0,
        turn_count=3,
    )

    hydrated = BenchmarkStore._attach_matrix_tool_turn_summary_fields(
        summary_rows=(summary_row,),
        request_rows=(first_request_row, second_request_row),
    )

    assert hydrated[0] is not summary_row
    assert hydrated[0].tool_call_count == 3
    assert hydrated[0].tool_latency_ms == 10.0
    assert hydrated[0].observation_bytes == 60
    assert hydrated[0].fatal_rate == 0.5
    assert hydrated[0].turn_count == 5


def test_attach_matrix_tool_turn_summary_fields_preserves_explicit_and_unmatched_rows() -> None:
    explicit_row = build_benchmark_matrix_summary_row(
        job_id="bench-matrix-explicit",
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
        repeats=1,
        requests=1,
        duration_seconds=0,
        ttft_mean_ms=24.45,
        ttft_std_ms=0.0,
        request_latency_mean_ms=88.4,
        request_latency_std_ms=0.0,
        prefill_tokens_per_second_mean=1400.0,
        decode_tokens_per_second_mean=58.2,
        throughput_requests_per_second=3.8,
        throughput_tokens_per_second=221.5,
        success_rate=1.0,
        peak_memory_bytes_max=2_147_483_648,
        queue_wait_mean_ms=5.1,
        queue_wait_p95_ms=9.2,
        tool_call_count=9,
    )
    unmatched_row = build_benchmark_matrix_summary_row(
        job_id="bench-matrix-unmatched",
        task_kind="text-generation",
        source_repo="HuggingFaceH4/ultrachat_200k",
        model_id="melix-dev-text",
        suite_id="other",
        context_length=512,
        generation_length=128,
        batch_size=2,
        cache_profile="cold",
        reasoning_mode="enabled",
        structured_output_mode="plain_text",
        concurrency_level=1,
        repeats=1,
        requests=1,
        duration_seconds=0,
        ttft_mean_ms=24.45,
        ttft_std_ms=0.0,
        request_latency_mean_ms=88.4,
        request_latency_std_ms=0.0,
        prefill_tokens_per_second_mean=1400.0,
        decode_tokens_per_second_mean=58.2,
        throughput_requests_per_second=3.8,
        throughput_tokens_per_second=221.5,
        success_rate=1.0,
        peak_memory_bytes_max=2_147_483_648,
        queue_wait_mean_ms=5.1,
        queue_wait_p95_ms=9.2,
    )
    request_row = build_benchmark_matrix_request_row(
        job_id="bench-matrix-explicit",
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
        tool_call_count=1,
    )

    hydrated = BenchmarkStore._attach_matrix_tool_turn_summary_fields(
        summary_rows=(explicit_row, unmatched_row),
        request_rows=(request_row,),
    )

    assert hydrated[0] is explicit_row
    assert hydrated[1] is unmatched_row
    assert BenchmarkStore._attach_matrix_tool_turn_summary_fields(
        summary_rows=(explicit_row,),
        request_rows=(),
    ) == (explicit_row,)


def test_attach_matrix_tool_turn_summary_fields_skips_zero_tool_turn_requests() -> None:
    summary_row = build_benchmark_matrix_summary_row(
        job_id="bench-matrix-zero-tool-turns",
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
        repeats=1,
        requests=1,
        duration_seconds=0,
        ttft_mean_ms=24.45,
        ttft_std_ms=0.0,
        request_latency_mean_ms=88.4,
        request_latency_std_ms=0.0,
        prefill_tokens_per_second_mean=1400.0,
        decode_tokens_per_second_mean=58.2,
        throughput_requests_per_second=3.8,
        throughput_tokens_per_second=221.5,
        success_rate=1.0,
        peak_memory_bytes_max=2_147_483_648,
        queue_wait_mean_ms=5.1,
        queue_wait_p95_ms=9.2,
    )
    request_row = build_benchmark_matrix_request_row(
        job_id="bench-matrix-zero-tool-turns",
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
    )

    hydrated = BenchmarkStore._attach_matrix_tool_turn_summary_fields(
        summary_rows=(summary_row,),
        request_rows=(request_row,),
    )

    assert hydrated[0] is summary_row


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


@pytest.mark.parametrize("probe_mode", ("off", "minimal", "definitely-not-a-mode", ""))
def test_persist_serving_benchmark_default_policy_skips_heavy_telemetry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    probe_mode: str,
) -> None:
    pytest.importorskip(
        "worker.productization.probe_policy",
        reason="probe policy foundation is expected from the main implementation",
    )
    monkeypatch.setenv("MELIX_PROBE_MODE", probe_mode)
    guard_production_safe_probe_paths(monkeypatch)

    jobs_root = tmp_path / "bench"
    job = build_serving_benchmark_job(
        job_id=f"bench-policy-{probe_mode or 'empty'}",
        model_id="melix-dev-text",
        suites=("smoke",),
        parameters={},
        status="completed",
        output_dir=str(jobs_root),
    )
    results = build_serving_benchmark_results(
        job_id=job.job_id,
        metrics={"bench.smoke.ttft_ms": 24.45},
        units={"bench.smoke.ttft_ms": "ms"},
        report_path=str(jobs_root / "bench-report.md"),
        report_markdown="# Melix Bench\n",
    )

    persisted = BenchmarkStore().persist_serving_benchmark(
        jobs_root=jobs_root,
        job=job,
        results=results,
    )

    evidence = json.loads(persisted["evidence"].read_text(encoding="utf-8"))
    assert evidence["schema_version"] == "melix.run_evidence.v1"
    assert evidence["run_id"] == job.job_id
    assert evidence["telemetry_summary"]["collector_status"] == "disabled"
    assert evidence["telemetry_summary"]["sample_count"] == 0
    assert persisted["telemetry_jsonl"] == jobs_root / "telemetry-samples.jsonl"
    telemetry_rows = [
        json.loads(line)
        for line in persisted["telemetry_jsonl"].read_text(encoding="utf-8").splitlines()
    ]
    assert telemetry_rows[0]["sample_kind"] == "telemetry_disabled"
