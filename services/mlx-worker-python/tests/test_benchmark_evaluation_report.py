from __future__ import annotations

import json
from pathlib import Path

import pytest

import worker.productization.benchmark_evaluation_report as benchmark_evaluation_report
from worker.productization.benchmark_evaluation_report import (
    _METRIC_DIRECTION_BY_KEY,
    _aggregate_probe_values,
    _benchmark_probe_label,
    _build_metric_row,
    _collect_benchmark_probe_metrics,
    _collect_evaluation_sample_probe_metrics,
    _collect_runtime_metadata,
    _dict_rows,
    _finalize_numeric_aggregate,
    _finalize_probe_aggregates,
    _label_part,
    _markdown_cell,
    _metric_direction,
    _metric_key_direction,
    _report_rows,
    _update_numeric_aggregate,
    _update_probe_aggregate_pairs,
    _update_probe_aggregates_by_label,
    ReportValidationError,
    assert_valid_report_payload,
    build_benchmark_evaluation_report,
    build_sticky_comment_body,
    load_report_input,
    render_markdown_report,
    render_terminal_report,
    validate_report_payload,
    write_report_outputs,
)


class _SparseProbeRow(dict[str, object]):
    def __init__(
        self,
        *args: object,
        forbidden_keys: set[str],
        forbid_contains: bool = False,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._forbidden_keys = forbidden_keys
        self._forbid_contains = forbid_contains

    def __contains__(self, key: object) -> bool:
        if self._forbid_contains and key in self._forbidden_keys:
            raise AssertionError(f"unexpected fixed-key membership scan for {key}")
        return super().__contains__(key)

    def get(self, key: str, default: object = None) -> object:
        if key in self._forbidden_keys:
            raise AssertionError(f"unexpected fixed-key scan for {key}")
        return super().get(key, default)


def _bundle(*, ttft_ms: float, tokens_per_second: float, accuracy: float) -> dict[str, object]:
    return {
        "export_schema_version": "melix.benchmark_export.v1",
        "benchmark_results": [
            {
                "job_id": "bench-1",
                "suite": "smoke",
                "metrics": [
                    {"name": "bench.smoke.ttft_ms", "value": ttft_ms, "unit": "ms"},
                    {
                        "name": "bench.smoke.tokens_per_second",
                        "value": tokens_per_second,
                        "unit": "tok/s",
                    },
                ],
            }
        ],
        "benchmark_matrix_summary_rows": [
            {
                "job_id": "matrix-1",
                "suite_id": "smoke",
                "context_length": 1024,
                "generation_length": 128,
                "batch_size": 1,
                "request_latency_mean_ms": ttft_ms * 3,
                "request_latency_p95_ms": ttft_ms * 3.5,
                "throughput_tokens_per_second": tokens_per_second * 4,
                "success_rate": 1.0,
                "failed_count": 0,
            }
        ],
        "evaluation_summary_rows": [
            {
                "job_id": "eval-1",
                "suite_id": "mmlu",
                "dataset_id": "mmlu.dev.v1",
                "primary_score_name": "typed_score_mean",
                "primary_score_value": accuracy,
                "sample_size": 8,
                "failure_count": 0,
                "duration_seconds": 10.0,
            }
        ],
    }


def test_load_report_input_accepts_batch_run_summary_bundle(tmp_path: Path) -> None:
    summary = {
        "schema_version": "melix.batch.run_summary.v1",
        "run_id": "batch-1",
        "status": "succeeded",
        "models": [
            {
                "model_index": "01",
                "repo_id": "mlx-community/Smoke-4bit",
                "status": "succeeded",
                "benchmark_job_id": "bench-1",
                "evaluation_job_id": "eval-1",
                "duration_seconds": 2.5,
                "metric_fields": {
                    "bench.smoke.tokens_per_second": 12.5,
                    "eval.event_extraction.semantic_f1": 0.9,
                },
            }
        ],
    }
    (tmp_path / "run-summary.json").write_text(json.dumps(summary), encoding="utf-8")

    bundle = load_report_input(tmp_path)

    assert bundle["export_schema_version"] == "melix.batch.summary_bundle.v1"
    assert bundle["batch_run_summary"] == summary
    report = build_benchmark_evaluation_report(baseline=bundle, candidate=bundle)
    metrics = {row["metric"]: row for row in report["metrics"]}
    assert metrics["bench.smoke.tokens_per_second"]["status"] == "ok"
    assert metrics["eval.event_extraction.semantic_f1"]["status"] == "ok"


def _run_evidence(
    *,
    run_id: str,
    run_kind: str,
    decode_ms: float,
    status: str,
    fallback_count: int = 0,
    system_power_w: float = 15.0,
    telemetry_failure_count: int = 0,
    include_process_attribution: bool = True,
) -> dict[str, object]:
    probes: list[dict[str, object]] = [
        {
            "run_id": run_id,
            "trace_id": f"{run_id}:trace",
            "span_id": f"{run_id}:decode",
            "parent_span_id": f"{run_id}:worker_dispatch",
            "component": "runtime",
            "phase": "decode",
            "started_at_monotonic_ms": 10,
            "duration_ms": decode_ms,
            "status": status,
            "error_stage": "decode" if status == "failed" else "",
            "error_code": "runtime_error" if status == "failed" else "",
            "attributes": {"suite_id": "smoke"},
        }
    ]
    if fallback_count:
        probes.append(
            {
                "run_id": run_id,
                "trace_id": f"{run_id}:trace",
                "span_id": f"{run_id}:fallback_enter",
                "parent_span_id": f"{run_id}:worker_dispatch",
                "component": "runtime",
                "phase": "fallback_enter",
                "started_at_monotonic_ms": 30,
                "duration_ms": 0.001,
                "status": "completed",
                "error_stage": "",
                "error_code": "",
                "attributes": {"fallback_count": fallback_count},
            }
        )
    telemetry_summary: dict[str, object] = {
        "schema_version": "melix.telemetry_summary.v1",
        "collector_status": "partial" if telemetry_failure_count else "collected",
        "time_series_path": "telemetry-samples.jsonl",
        "telemetry_failures": ["powermetrics_failed:fixture"] * telemetry_failure_count,
        "average_system_power_w": system_power_w,
        "peak_system_power_w": system_power_w + 1.0,
        "watts_per_output_token": system_power_w / 10.0,
        "sample_count": 2,
    }
    if include_process_attribution:
        telemetry_summary["process_attribution"] = {
            "primary_runtime_process": {
                "pid": 101,
                "name": "mlx-runner",
                "role": "primary_runtime",
                "port": 12434,
                "bundle_prefix": "com.melix",
                "peak_memory_bytes": 4096,
                "avg_cpu_percent": 12.5,
                "sample_count": 2,
            },
            "control_plane_process": {
                "pid": 102,
                "name": "melix-control",
                "role": "control_plane",
                "port": 11434,
                "bundle_prefix": "com.melix",
                "peak_memory_bytes": 2048,
                "avg_cpu_percent": 2.5,
                "sample_count": 2,
            },
            "worker_processes": [
                {
                    "pid": 103,
                    "name": "melix-worker",
                    "role": "worker",
                    "port": 0,
                    "bundle_prefix": "com.melix",
                    "peak_memory_bytes": 1024,
                    "avg_cpu_percent": 4.5,
                    "sample_count": 2,
                }
            ],
            "external_provider_processes": [],
            "process_tree_summary": {"roles": ["primary_runtime", "control_plane", "worker"]},
        }
    model_memory_summary = {
        "runtime_model_handle": f"{run_id}-model::1",
        "runtime_model_id": "mlx-community/test-model",
        "runtime_kind": "text",
        "runtime_name": "mlx-text",
        "loaded_model_estimated_resident_bytes": 4096,
        "runtime_stats_model_resident_bytes": 4096,
        "runtime_stats_resident_bytes": 5120,
        "runtime_stats_cache_resident_bytes": 1024,
        "runtime_stats_kv_cache_bytes": 0,
        "runtime_stats_memory_headroom_bytes": 0,
        "load_triggered_by_run": True,
        "load_rss_before_bytes": 10000,
        "load_rss_after_bytes": 15000,
        "load_rss_delta_bytes": 5000,
        "measurement_scope": "worker_registry",
    }
    return {
        "schema_version": "melix.run_evidence.v1",
        "run_id": run_id,
        "melix_commit": "abc123",
        "git_branch": "codex/report-json-export",
        "dirty_worktree": False,
        "run_kind": run_kind,
        "started_at": 1_779_000_000_000,
        "ended_at": 1_779_000_001_000,
        "duration_ms": 1000,
        "status": status,
        "command": "melix evidence fixture",
        "artifact_root": f"/tmp/{run_id}",
        "target_model_id": "mlx-community/test-model",
        "hf_repo_id": "mlx-community/test-model",
        "task_kind": "text-generation",
        "model_snapshot": "model-sha",
        "adapter_id": "adapter-a",
        "adapter_snapshot": "adapter-sha",
        "runtime_kind": "mlx",
        "runtime_config": {"quantization": "4bit"},
        "dataset_ref": "fixture.dataset",
        "dataset_revision": "dataset-sha",
        "suite_id": "smoke",
        "sample_count": 1,
        "input_digest": "input-sha",
        "prompt_template_digest": "prompt-sha",
        "generation_config": {"max_tokens": 16},
        "metrics": [{"name": "decode_ms", "value": decode_ms, "unit": "ms"}],
        "probe_timeline": probes,
        "telemetry_summary": telemetry_summary,
        "model_memory_summary": model_memory_summary,
        "artifacts": [{"kind": "probe_timeline", "path": "probes.jsonl", "role": "diagnostic"}],
        "failure_summary": {"failed": status == "failed"},
        "fallback_summary": {"fallback_count": fallback_count},
    }


def _evaluation_run_evidence_with_sample_probes(
    *,
    run_id: str,
    aggregate_decode_ms: float,
    detail_decode_ms: float,
    failed_count: int,
) -> dict[str, object]:
    return {
        "schema_version": "melix.run_evidence.v1",
        "run_id": run_id,
        "run_kind": "evaluation",
        "probe_timeline": [
            {
                "run_id": run_id,
                "trace_id": f"{run_id}:trace",
                "span_id": f"{run_id}:sample_select:aggregate",
                "parent_span_id": f"{run_id}:worker_dispatch",
                "component": "worker",
                "phase": "sample_select",
                "started_at_monotonic_ms": 5,
                "duration_ms": 0.001,
                "status": "completed",
                "error_stage": "",
                "error_code": "",
                "attributes": [],
            },
            {
                "run_id": run_id,
                "trace_id": f"{run_id}:trace",
                "span_id": f"{run_id}:decode:aggregate",
                "parent_span_id": f"{run_id}:worker_dispatch",
                "component": "runtime",
                "phase": "decode",
                "started_at_monotonic_ms": 10,
                "duration_ms": aggregate_decode_ms,
                "status": "completed",
                "error_stage": "",
                "error_code": "",
                "attributes": {
                    "probe_kind": "aggregate_summary",
                    "sample_count": 10,
                },
            },
            {
                "run_id": run_id,
                "trace_id": f"{run_id}:trace",
                "span_id": f"{run_id}:decode:detail",
                "parent_span_id": f"{run_id}:worker_dispatch",
                "component": "runtime",
                "phase": "decode",
                "started_at_monotonic_ms": 20,
                "duration_ms": detail_decode_ms,
                "status": "completed",
                "error_stage": "",
                "error_code": "",
                "attributes": {
                    "probe_kind": "sample_detail",
                    "sample_id": "sample-slow",
                },
            },
            {
                "run_id": run_id,
                "trace_id": f"{run_id}:trace",
                "span_id": f"{run_id}:aggregate_result:aggregate",
                "parent_span_id": f"{run_id}:worker_dispatch",
                "component": "worker",
                "phase": "aggregate_result",
                "started_at_monotonic_ms": 30,
                "duration_ms": 1.0,
                "status": "completed",
                "error_stage": "",
                "error_code": "",
                "attributes": {
                    "probe_kind": "aggregate_summary",
                    "sample_count": 10,
                    "failed_count": failed_count,
                },
            },
            {
                "run_id": run_id,
                "trace_id": f"{run_id}:trace",
                "span_id": f"{run_id}:fallback_enter:aggregate",
                "parent_span_id": f"{run_id}:worker_dispatch",
                "component": "runtime",
                "phase": "fallback_enter",
                "started_at_monotonic_ms": 35,
                "duration_ms": 0.001,
                "status": "completed",
                "error_stage": "",
                "error_code": "",
                "attributes": {
                    "probe_kind": "aggregate_summary",
                    "sample_count": 10,
                    "fallback_sample_count": 1,
                },
            },
            {
                "run_id": run_id,
                "trace_id": f"{run_id}:trace",
                "span_id": f"{run_id}:aggregate_result:detail",
                "parent_span_id": f"{run_id}:worker_dispatch",
                "component": "worker",
                "phase": "aggregate_result",
                "started_at_monotonic_ms": 40,
                "duration_ms": 2.0,
                "status": "failed",
                "error_stage": "aggregate_result",
                "error_code": "parse_error",
                "attributes": {
                    "probe_kind": "sample_detail",
                    "sample_id": "sample-failed",
                },
            },
        ],
    }


def test_report_builder_computes_direction_aware_deltas() -> None:
    report = build_benchmark_evaluation_report(
        baseline=_bundle(ttft_ms=100.0, tokens_per_second=50.0, accuracy=0.8),
        candidate=_bundle(ttft_ms=112.0, tokens_per_second=55.0, accuracy=0.75),
    )

    rows_by_metric = {row["metric"]: row for row in report["rows"]}

    assert rows_by_metric["bench.smoke.ttft_ms"]["status"] == "warning"
    assert rows_by_metric["bench.smoke.ttft_ms"]["direction"] == "lower_is_better"
    assert rows_by_metric["bench.smoke.ttft_ms"]["delta_pct"] == pytest.approx(12.0)
    assert rows_by_metric["bench.smoke.tokens_per_second"]["status"] == "ok"
    assert rows_by_metric["bench.smoke.tokens_per_second"]["direction"] == "higher_is_better"
    assert rows_by_metric["eval.mmlu.typed_score_mean"]["status"] == "warning"
    assert rows_by_metric["eval.mmlu.typed_score_mean"]["delta"] == pytest.approx(-0.05)
    assert (
        rows_by_metric["bench.matrix.smoke.ctx1024.gen128.b1.c0.request_latency_p95_ms"][
            "status"
        ]
        == "warning"
    )
    assert report["summary"]["warning_count"] == 4
    assert report["summary"]["status"] == "warning"


def test_metric_direction_reuses_metric_key_cache_for_repeated_suffixes() -> None:
    _metric_key_direction.cache_clear()

    assert _metric_direction("bench.context.ctx1024.prefill_ms_mean") == "lower_is_better"
    assert _metric_direction("bench.context.ctx2048.prefill_ms_mean") == "lower_is_better"

    cache_info = _metric_key_direction.cache_info()
    assert cache_info.misses == 1
    assert cache_info.hits == 1


def test_report_builder_warns_on_zero_baseline_regressions() -> None:
    baseline = {
        "benchmark_matrix_summary_rows": [
            {
                "suite_id": "smoke",
                "context_length": 1024,
                "generation_length": 128,
                "batch_size": 1,
                "concurrency_level": 1,
                "failed_count": 0,
            }
        ]
    }
    candidate = {
        "benchmark_matrix_summary_rows": [
            {
                "suite_id": "smoke",
                "context_length": 1024,
                "generation_length": 128,
                "batch_size": 1,
                "concurrency_level": 1,
                "failed_count": 1,
            }
        ]
    }

    report = build_benchmark_evaluation_report(baseline=baseline, candidate=candidate)

    rows_by_metric = {row["metric"]: row for row in report["rows"]}
    row = rows_by_metric["bench.matrix.smoke.ctx1024.gen128.b1.c1.failed_count"]

    assert row["delta_pct"] is None
    assert row["status"] == "warning"


def test_report_builder_treats_cache_hit_rate_as_higher_is_better() -> None:
    baseline = {
        "benchmark_context_rows": [
            {
                "suite": "smoke",
                "context_length": 128,
                "generation_length": 32,
                "batch_size": 1,
                "cache_hit": True,
            }
        ]
    }
    candidate = {
        "benchmark_context_rows": [
            {
                "suite": "smoke",
                "context_length": 128,
                "generation_length": 32,
                "batch_size": 1,
                "cache_hit": False,
            }
        ]
    }

    report = build_benchmark_evaluation_report(baseline=baseline, candidate=candidate)

    rows_by_metric = {row["metric"]: row for row in report["rows"]}
    row = rows_by_metric["bench.context.smoke.ctx128.gen32.b1.cache_hit_rate"]

    assert row["direction"] == "higher_is_better"
    assert row["status"] == "warning"


def test_report_builder_collects_serving_benchmark_request_phase_rows() -> None:
    baseline = {
        "benchmark_request_rows": [
            {
                "suite": "agentic_visit",
                "context_length": 64,
                "generation_length": 16,
                "batch_size": 1,
                "phase": "tool_turn",
                "phase_index": 0,
                "tool_call_count": 1,
                "tool_latency_ms": 5.0,
                "observation_bytes": 64,
                "fatal_rate": 0.0,
                "turn_count": 2,
            },
            {
                "suite": "agentic_visit",
                "context_length": 64,
                "generation_length": 16,
                "batch_size": 1,
                "phase": "final_answer",
                "phase_index": 1,
                "duration_ms": 40.0,
                "request_latency_ms": 40.0,
                "ttft_ms": 10.0,
            }
        ]
    }
    candidate = {
        "benchmark_request_rows": [
            {
                "suite": "agentic_visit",
                "context_length": 64,
                "generation_length": 16,
                "batch_size": 1,
                "phase": "tool_turn",
                "phase_index": 0,
                "tool_call_count": 1,
                "tool_latency_ms": 7.0,
                "observation_bytes": 80,
                "fatal_rate": 1.0,
                "turn_count": 2,
            },
            {
                "suite": "agentic_visit",
                "context_length": 64,
                "generation_length": 16,
                "batch_size": 1,
                "phase": "final_answer",
                "phase_index": 1,
                "duration_ms": 50.0,
                "request_latency_ms": 50.0,
                "ttft_ms": 12.0,
            }
        ]
    }

    report = build_benchmark_evaluation_report(baseline=baseline, candidate=candidate)

    rows_by_metric = {row["metric"]: row for row in report["rows"]}
    label = "bench.request.agentic_visit.ctx64.gen16.b1.tool_turn"
    final_answer_label = "bench.request.agentic_visit.ctx64.gen16.b1.final_answer"

    assert rows_by_metric[f"{label}.tool_latency_ms_mean"]["status"] == "warning"
    assert rows_by_metric[f"{label}.fatal_rate_rate"]["direction"] == "lower_is_better"
    assert rows_by_metric[f"{final_answer_label}.request_latency_ms_mean"]["status"] == "warning"
    assert rows_by_metric[f"{final_answer_label}.ttft_ms_mean"]["direction"] == "lower_is_better"


def test_collect_runtime_metadata_preserves_key_order_with_sparse_values() -> None:
    metrics: dict[str, object] = {}

    _collect_runtime_metadata(
        metrics,
        [
            {
                "parameters": {
                    "runtime_model_id": "target/head",
                    "runtime_kind": "swift-text",
                }
            },
            {
                "parameters": {
                    "runtime_kind": "python-worker",
                    "runtime_model_id": "target/base",
                    "unused_runtime_value": "ignored",
                }
            },
            {"parameters": {"runtime_model_id": ""}},
            {"parameters": "invalid"},
        ],
        prefix="bench.runtime",
    )

    assert metrics == {
        "bench.runtime.runtime_kind": "python-worker,swift-text",
        "bench.runtime.runtime_model_id": "target/base,target/head",
    }


def test_report_builder_includes_runtime_metadata_and_decode_probes() -> None:
    baseline = {
        "benchmark_matrix_jobs": [
            {
                "job_id": "matrix-base",
                "parameters": {
                    "runtime_kind": "swift-text",
                    "runtime_model_id": "target/base",
                },
            }
        ],
        "benchmark_matrix_request_rows": [
            {
                "suite_id": "smoke",
                "context_length": 1024,
                "generation_length": 128,
                "batch_size": 1,
                "concurrency_level": 1,
                "speculative_acceptance_rate": 0.75,
                "speculative_rejected_tokens": 2,
                "speculative_fallback_count": 0,
                "speculative_draft_propose_ms": 8.0,
                "speculative_target_verify_ms": 12.0,
                "dflash_enabled": True,
                "dflash_rollback_count": 1,
            }
        ],
    }
    candidate = {
        "benchmark_matrix_jobs": [
            {
                "job_id": "matrix-head",
                "parameters": {
                    "runtime_kind": "swift-text",
                    "runtime_model_id": "target/head",
                },
            }
        ],
        "benchmark_matrix_request_rows": [
            {
                "suite_id": "smoke",
                "context_length": 1024,
                "generation_length": 128,
                "batch_size": 1,
                "concurrency_level": 1,
                "speculative_acceptance_rate": 0.80,
                "speculative_rejected_tokens": 4,
                "speculative_fallback_count": 1,
                "speculative_draft_propose_ms": 9.0,
                "speculative_target_verify_ms": 11.0,
                "dflash_enabled": True,
                "dflash_rollback_count": 2,
            }
        ],
    }

    report = build_benchmark_evaluation_report(baseline=baseline, candidate=candidate)

    rows_by_metric = {row["metric"]: row for row in report["rows"]}
    label = "bench.matrix.request.smoke.ctx1024.gen128.b1.c1"

    assert rows_by_metric["bench.matrix.runtime.runtime_kind"]["status"] == "ok"
    assert rows_by_metric["bench.matrix.runtime.runtime_model_id"]["status"] == "not_comparable"
    assert rows_by_metric[f"{label}.speculative_acceptance_rate_mean"]["direction"] == (
        "higher_is_better"
    )
    assert rows_by_metric[f"{label}.speculative_acceptance_rate_mean"]["status"] == "ok"
    assert rows_by_metric[f"{label}.speculative_rejected_tokens_sum"]["status"] == "warning"
    assert rows_by_metric[f"{label}.speculative_fallback_count_sum"]["direction"] == (
        "lower_is_better"
    )
    assert rows_by_metric[f"{label}.dflash_rollback_count_sum"]["status"] == "warning"
    assert rows_by_metric[f"{label}.dflash_enabled_rate"]["status"] == "ok"
    assert report["summary"]["warning_count"] == 4


def test_numeric_aggregate_helpers_track_running_totals() -> None:
    aggregate = None
    aggregate = _update_numeric_aggregate(aggregate, 3.0)
    aggregate = _update_numeric_aggregate(aggregate, 5.0)

    assert aggregate == (8.0, 2)
    assert _finalize_numeric_aggregate("prefill_ms", aggregate) == ("mean", 4.0)
    assert _finalize_numeric_aggregate("cache_hit", aggregate) == ("rate", 4.0)
    assert _finalize_numeric_aggregate("speculative_fallback_count", aggregate) == ("sum", 8.0)


def test_collect_benchmark_probe_metrics_groups_aggregates_by_label_and_preserves_metrics() -> None:
    row_a = _SparseProbeRow(
        {
            "suite_id": "smoke",
            "context_length": 1024,
            "generation_length": 128,
            "batch_size": 1,
            "concurrency_level": 1,
            "prefill_ms": 10.0,
            "decode_ms": 20.0,
            "speculative_fallback_count": 1,
        },
        forbidden_keys={"prefill_ms", "decode_ms", "speculative_fallback_count"},
    )
    row_b = _SparseProbeRow(
        {
            "suite_id": "smoke",
            "context_length": 1024,
            "generation_length": 128,
            "batch_size": 1,
            "concurrency_level": 1,
            "prefill_ms": 14.0,
            "decode_ms": 24.0,
            "speculative_fallback_count": 3,
        },
        forbidden_keys={"prefill_ms", "decode_ms", "speculative_fallback_count"},
    )

    aggregates_by_label: dict[str, dict[str, tuple[float, int]]] = {}
    _update_probe_aggregates_by_label(aggregates_by_label, label="shared", key="prefill_ms", value=10.0)
    _update_probe_aggregates_by_label(aggregates_by_label, label="shared", key="prefill_ms", value=14.0)
    _update_probe_aggregates_by_label(aggregates_by_label, label="shared", key="decode_ms", value=20.0)

    assert aggregates_by_label == {
        "shared": {
            "prefill_ms": (24.0, 2),
            "decode_ms": (20.0, 1),
        }
    }

    aggregate_pairs: dict[tuple[str, str], tuple[float, int]] = {}
    _update_probe_aggregate_pairs(aggregate_pairs, label="shared", key="prefill_ms", value=10.0)
    _update_probe_aggregate_pairs(aggregate_pairs, label="shared", key="prefill_ms", value=14.0)
    _update_probe_aggregate_pairs(aggregate_pairs, label="shared", key="decode_ms", value=20.0)
    _update_probe_aggregate_pairs(
        aggregate_pairs,
        label="shared",
        key="speculative_fallback_count",
        value=4.0,
    )

    assert aggregate_pairs == {
        ("shared", "prefill_ms"): (24.0, 2),
        ("shared", "decode_ms"): (20.0, 1),
        ("shared", "speculative_fallback_count"): (4.0, 1),
    }
    assert _finalize_probe_aggregates(aggregate_pairs, prefix="bench") == {
        "bench.shared.prefill_ms_mean": 12.0,
        "bench.shared.decode_ms_mean": 20.0,
        "bench.shared.speculative_fallback_count_sum": 4.0,
    }

    metrics: dict[str, object] = {}
    _collect_benchmark_probe_metrics(metrics, [row_a, row_b], prefix="bench")

    label = "smoke.ctx1024.gen128.b1.c1"
    assert metrics == {
        f"bench.{label}.prefill_ms_mean": 12.0,
        f"bench.{label}.decode_ms_mean": 22.0,
        f"bench.{label}.speculative_fallback_count_sum": 4.0,
    }


def test_metric_direction_caches_full_metric_names() -> None:
    _metric_direction.cache_clear()

    assert _metric_direction("bench.smoke.prefill_ms") == "lower_is_better"
    assert _metric_direction("bench.smoke.prefill_ms") == "lower_is_better"

    assert _metric_direction.cache_info().hits == 1


def test_metric_row_fast_paths_exact_numeric_values(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed_values: list[object] = []
    original = benchmark_evaluation_report._float_or_none

    def tracked_float_or_none(value: object) -> float | None:
        parsed_values.append(value)
        return original(value)

    monkeypatch.setattr(benchmark_evaluation_report, "_float_or_none", tracked_float_or_none)

    numeric_row = _build_metric_row(metric_name="bench.smoke.prefill_ms", baseline=10.0, candidate=12)
    bool_row = _build_metric_row(metric_name="bench.smoke.cache_hit", baseline=True, candidate=False)
    metadata_row = _build_metric_row(metric_name="bench.smoke.runtime_kind", baseline="mlx", candidate="mlx")

    assert parsed_values == ["mlx", "mlx"]
    assert numeric_row["delta"] == 2.0
    assert numeric_row["direction"] == "lower_is_better"
    assert bool_row["baseline"] == 1.0
    assert bool_row["candidate"] == 0.0
    assert metadata_row["status"] == "ok"


def test_probe_collectors_fast_path_exact_numeric_values(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed_values: list[object] = []
    original = benchmark_evaluation_report._float_or_none

    def tracked_float_or_none(value: object) -> float | None:
        parsed_values.append(value)
        return original(value)

    monkeypatch.setattr(benchmark_evaluation_report, "_float_or_none", tracked_float_or_none)

    benchmark_metrics: dict[str, object] = {}
    _collect_benchmark_probe_metrics(
        benchmark_metrics,
        [
            {
                "suite_id": "smoke",
                "context_length": 1024,
                "generation_length": 128,
                "batch_size": 1,
                "concurrency_level": 1,
                "prefill_ms": 10.0,
                "decode_ms": 20,
                "cache_hit": True,
                "warmup_ms": "2.5",
            }
        ],
        prefix="bench",
    )
    evaluation_metrics: dict[str, object] = {}
    _collect_evaluation_sample_probe_metrics(
        evaluation_metrics,
        [
            {
                "suite_id": "smoke",
                "sample_render_ms": 3.0,
                "inference_ms": 4,
                "validation_ms": False,
                "scoring_ms": "5.5",
            }
        ],
    )

    assert parsed_values == ["2.5", "5.5"]
    assert benchmark_metrics["bench.smoke.ctx1024.gen128.b1.c1.prefill_ms_mean"] == 10.0
    assert benchmark_metrics["bench.smoke.ctx1024.gen128.b1.c1.decode_ms_mean"] == 20.0
    assert benchmark_metrics["bench.smoke.ctx1024.gen128.b1.c1.cache_hit_rate"] == 1.0
    assert evaluation_metrics["eval.sample.smoke.sample_render_ms_mean"] == 3.0
    assert evaluation_metrics["eval.sample.smoke.inference_ms_mean"] == 4.0
    assert evaluation_metrics["eval.sample.smoke.validation_ms_mean"] == 0.0


def test_evaluation_sample_collector_finalizes_mean_metrics_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_finalize_numeric_aggregate(
        key: str,
        aggregate: tuple[float, int] | None,
    ) -> tuple[str, float]:
        del aggregate
        raise AssertionError(f"unexpected generic aggregate finalizer for {key}")

    monkeypatch.setattr(
        benchmark_evaluation_report,
        "_finalize_numeric_aggregate",
        fail_finalize_numeric_aggregate,
    )

    metrics: dict[str, object] = {}
    _collect_evaluation_sample_probe_metrics(
        metrics,
        [
            {"suite_id": "smoke", "sample_render_ms": 3.0},
            {"suite_id": "smoke", "sample_render_ms": 5.0},
        ],
    )

    assert metrics == {"eval.sample.smoke.sample_render_ms_mean": 4.0}


def test_evaluation_sample_collector_aggregates_agentic_tool_metrics() -> None:
    metrics: dict[str, object] = {}

    _collect_evaluation_sample_probe_metrics(
        metrics,
        [
            {
                "suite_id": "agentic",
                "agentic_tool_metrics": {
                    "agentic_tool.call_count": 2.0,
                    "agentic_tool.completed_count": 2.0,
                    "agentic_tool.observation_emitted_bytes": 40.0,
                },
            },
            {
                "suite_id": "agentic",
                "agentic_tool_metrics": {
                    "agentic_tool.call_count": 4.0,
                    "agentic_tool.completed_count": 3.0,
                    "agentic_tool.failed_count": 1.0,
                    "agentic_tool.observation_emitted_bytes": 80.0,
                },
            },
        ],
    )

    assert metrics["eval.sample.agentic.agentic_tool.call_count_mean"] == 3.0
    assert metrics["eval.sample.agentic.agentic_tool.completed_count_mean"] == 2.5
    assert metrics["eval.sample.agentic.agentic_tool.failed_count_mean"] == 1.0
    assert metrics["eval.sample.agentic.agentic_tool.observation_emitted_bytes_mean"] == 60.0


def test_benchmark_probe_collector_aggregates_agentic_tool_metrics() -> None:
    metrics: dict[str, object] = {}

    _collect_benchmark_probe_metrics(
        metrics,
        [
            {
                "suite_id": "agentic",
                "context_length": 64,
                "generation_length": 16,
                "batch_size": 1,
                "agentic_tool_metrics": {
                    "agentic_tool.call_count": 1.0,
                    "agentic_tool.completed_count": 1.0,
                    "agentic_tool.latency_ms": 5.0,
                    "agentic_tool.observation_emitted_bytes": 20.0,
                },
                "tool_call_count": 1,
                "tool_latency_ms": 5.0,
                "observation_bytes": 20,
                "fatal_rate": 0.0,
                "turn_count": 2,
            },
            {
                "suite_id": "agentic",
                "context_length": 64,
                "generation_length": 16,
                "batch_size": 1,
                "agentic_tool_metrics": {
                    "agentic_tool.call_count": 3.0,
                    "agentic_tool.completed_count": 2.0,
                    "agentic_tool.failed_count": 1.0,
                    "agentic_tool.latency_ms": 15.0,
                    "agentic_tool.observation_emitted_bytes": 40.0,
                },
                "tool_call_count": 3,
                "tool_latency_ms": 15.0,
                "observation_bytes": 40,
                "fatal_rate": 1.0,
                "turn_count": 6,
            },
        ],
        prefix="bench.context",
    )

    label = "agentic.ctx64.gen16.b1"
    assert metrics[f"bench.context.{label}.agentic_tool.call_count_mean"] == 2.0
    assert metrics[f"bench.context.{label}.agentic_tool.completed_count_mean"] == 1.5
    assert metrics[f"bench.context.{label}.agentic_tool.failed_count_mean"] == 1.0
    assert metrics[f"bench.context.{label}.agentic_tool.latency_ms_mean"] == 10.0
    assert metrics[f"bench.context.{label}.agentic_tool.observation_emitted_bytes_mean"] == 30.0
    assert metrics[f"bench.context.{label}.tool_call_count_sum"] == 4.0
    assert metrics[f"bench.context.{label}.tool_latency_ms_mean"] == 10.0
    assert metrics[f"bench.context.{label}.observation_bytes_sum"] == 60.0
    assert metrics[f"bench.context.{label}.fatal_rate_rate"] == 0.5
    assert metrics[f"bench.context.{label}.turn_count_sum"] == 8.0


def test_probe_collectors_use_expected_sparse_row_scan_strategy() -> None:
    class NoContainsDict(dict[str, object]):
        def __contains__(self, key: object) -> bool:
            if key in {"prefill_ms", "decode_ms", "tokens_in", "dflash_enabled"}:
                raise AssertionError("benchmark collector should scan actual row items")
            return super().__contains__(key)

    class NoItemsDict(dict[str, object]):
        def items(self):  # type: ignore[override]
            raise AssertionError("evaluation collector should scan registered probe keys directly")

    benchmark_metrics: dict[str, object] = {}
    _collect_benchmark_probe_metrics(
        benchmark_metrics,
        [
            NoContainsDict(
                {
                    "suite_id": "smoke",
                    "context_length": 1024,
                    "generation_length": 128,
                    "batch_size": 1,
                    "concurrency_level": 2,
                    "prefill_ms": 10.0,
                    "irrelevant_payload": "skip",
                }
            )
        ],
        prefix="bench",
    )

    evaluation_metrics: dict[str, object] = {}
    _collect_evaluation_sample_probe_metrics(
        evaluation_metrics,
        [
            NoItemsDict(
                {
                    "suite_id": "smoke",
                    "sample_render_ms": 3.0,
                    "irrelevant_payload": "skip",
                }
            )
        ],
    )

    assert benchmark_metrics["bench.smoke.ctx1024.gen128.b1.c2.prefill_ms_mean"] == 10.0
    assert evaluation_metrics["eval.sample.smoke.sample_render_ms_mean"] == 3.0


def test_collect_benchmark_probe_metrics_reuses_matrix_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    original = benchmark_evaluation_report._matrix_label
    matrix_label_calls = 0

    def tracked_matrix_label(
        row: dict[str, object],
        *,
        label_cache: dict[tuple[str, str, str, str, str, str, str], str] | None = None,
    ) -> str:
        nonlocal matrix_label_calls
        matrix_label_calls += 1
        return original(row, label_cache=label_cache)

    monkeypatch.setattr(benchmark_evaluation_report, "_matrix_label", tracked_matrix_label)
    rows = [
        {
            "suite_id": "smoke",
            "context_length": 1024,
            "generation_length": 128,
            "batch_size": 1,
            "concurrency_level": 4,
            "prefill_ms": float(index),
        }
        for index in range(5)
    ]

    metrics: dict[str, object] = {}
    _collect_benchmark_probe_metrics(metrics, rows, prefix="bench")

    assert matrix_label_calls == 1
    assert metrics["bench.smoke.ctx1024.gen128.b1.c4.prefill_ms_mean"] == 2.0


def test_dict_rows_returns_lazy_iterable_of_dict_rows() -> None:
    rows = [{"name": "first"}, "skip", {"name": "second"}]

    filtered_rows = _dict_rows(rows)

    assert not isinstance(filtered_rows, list)
    assert list(filtered_rows) == [{"name": "first"}, {"name": "second"}]


def test_aggregate_probe_values_handles_empty_inputs() -> None:
    assert _aggregate_probe_values("prefill_ms", []) == ("mean", 0.0)
    assert _aggregate_probe_values("cache_hit", []) == ("rate", 0.0)
    assert _aggregate_probe_values("speculative_fallback_count", []) == ("sum", 0.0)


def test_benchmark_probe_label_cache_reuses_identical_shapes(monkeypatch: pytest.MonkeyPatch) -> None:
    original = benchmark_evaluation_report._build_benchmark_label
    built_keys: list[tuple[str, str, str, str, str, str, str]] = []

    def tracked(key: tuple[str, str, str, str, str, str, str]) -> str:
        built_keys.append(key)
        return original(key)

    monkeypatch.setattr(benchmark_evaluation_report, "_build_benchmark_label", tracked)

    cache: dict[tuple[str, str, str, str, str, str, str], str] = {}
    context_row = {
        "suite": "smoke suite",
        "context_length": 128,
        "generation_length": 32,
        "batch_size": 1,
    }
    matrix_row = {
        "suite_id": "smoke suite",
        "context_length": 128,
        "generation_length": 32,
        "batch_size": 1,
        "concurrency_level": 2,
    }

    assert (
        benchmark_evaluation_report._benchmark_probe_label(context_row, label_cache=cache)
        == "smoke_suite.ctx128.gen32.b1"
    )
    assert (
        benchmark_evaluation_report._benchmark_probe_label(
            {**context_row, "prefill_ms": 7.0},
            label_cache=cache,
        )
        == "smoke_suite.ctx128.gen32.b1"
    )
    assert benchmark_evaluation_report._matrix_label(matrix_row, label_cache=cache) == (
        "smoke_suite.ctx128.gen32.b1.c2"
    )
    assert (
        benchmark_evaluation_report._benchmark_probe_label(
            {**matrix_row, "prefill_ms": 9.0},
            label_cache=cache,
        )
        == "smoke_suite.ctx128.gen32.b1.c2"
    )

    assert built_keys == [
        ("bench", "smoke suite", "128", "32", "1", "", ""),
        ("matrix", "smoke suite", "128", "32", "1", "2", ""),
    ]


def test_benchmark_probe_label_cache_preserves_stringified_shape_boundaries() -> None:
    cache: dict[tuple[str, str, str, str, str, str, str], str] = {}

    numeric_row = {
        "suite": "shape",
        "context_length": 1,
        "generation_length": 2,
        "batch_size": True,
    }
    float_row = {
        "suite": "shape",
        "context_length": 1.0,
        "generation_length": 2,
        "batch_size": 1,
    }
    unhashable_row = {
        "suite": ["shape", "list"],
        "context_length": {"nested": "value"},
        "generation_length": 2,
        "batch_size": 1,
    }

    assert benchmark_evaluation_report._benchmark_probe_label(numeric_row, label_cache=cache) == (
        "shape.ctx1.gen2.bTrue"
    )
    assert benchmark_evaluation_report._benchmark_probe_label(float_row) == "shape.ctx1.0.gen2.b1"
    assert benchmark_evaluation_report._benchmark_probe_label(float_row, label_cache=cache) == (
        "shape.ctx1.0.gen2.b1"
    )
    assert benchmark_evaluation_report._benchmark_probe_label(unhashable_row, label_cache=cache) == (
        "['shape',_'list'].ctx{'nested':_'value'}.gen2.b1"
    )


def test_row_iterators_filter_invalid_entries_without_materializing_copies() -> None:
    report = {"rows": [{"metric": "bench.smoke.ttft_ms"}, "skip", {"metric": "eval.mmlu.score"}]}
    payload = [{"suite_id": "mmlu"}, None, {"suite_id": "gsm8k"}]

    assert tuple(_report_rows(report)) == (
        {"metric": "bench.smoke.ttft_ms"},
        {"metric": "eval.mmlu.score"},
    )
    assert tuple(_dict_rows(payload)) == ({"suite_id": "mmlu"}, {"suite_id": "gsm8k"})
    assert tuple(_report_rows({"rows": "not-a-list"})) == ()
    assert tuple(_dict_rows("not-a-list")) == ()


def test_report_builder_reports_missing_metrics_and_non_numeric_status() -> None:
    missing_report = build_benchmark_evaluation_report(
        baseline={"benchmark_results": [{"metrics": [{"name": "bench.smoke.ttft_ms", "value": 100.0}]}]},
        candidate={"benchmark_results": []},
    )
    missing_row = missing_report["rows"][0]

    assert missing_row["status"] == "missing"
    assert missing_report["summary"]["status"] == "missing"
    assert _markdown_cell(render_terminal_report(missing_report)).find("-") >= 0

    comparable_runtime_report = build_benchmark_evaluation_report(
        baseline={
            "benchmark_jobs": [
                {"parameters": "legacy"},
                {"parameters": {"runtime_kind": "text", "runtime_model_id": "base"}},
            ]
        },
        candidate={"benchmark_jobs": [{"parameters": {"runtime_kind": "text", "runtime_model_id": "head"}}]},
    )
    rows_by_metric = {row["metric"]: row for row in comparable_runtime_report["rows"]}

    assert comparable_runtime_report["summary"]["status"] == "not_comparable"
    assert rows_by_metric["bench.runtime.runtime_kind"]["status"] == "ok"
    assert rows_by_metric["bench.runtime.runtime_model_id"]["status"] == "not_comparable"


def test_report_builder_counts_statuses_in_one_pass() -> None:
    report = build_benchmark_evaluation_report(
        baseline={
            "benchmark_jobs": [{"parameters": {"runtime_model_id": "base"}}],
            "benchmark_results": [
                {
                    "metrics": [
                        {"name": "bench.smoke.ttft_ms", "value": 100.0},
                        {"name": "bench.smoke.tokens_per_second", "value": 100.0},
                    ]
                }
            ],
        },
        candidate={
            "benchmark_jobs": [{"parameters": {"runtime_model_id": "candidate"}}],
            "benchmark_results": [
                {
                    "metrics": [
                        {"name": "bench.smoke.ttft_ms", "value": 106.0},
                    ]
                }
            ],
        },
    )

    assert report["summary"] == {
        "status": "warning",
        "metric_count": 3,
        "warning_count": 1,
        "missing_count": 1,
        "not_comparable_count": 1,
    }


def test_report_builder_ignores_non_list_row_sets() -> None:
    report = build_benchmark_evaluation_report(
        baseline={"benchmark_results": {"metrics": []}},
        candidate={"benchmark_results": {"metrics": []}},
    )

    assert report["rows"] == []
    assert report["summary"]["status"] == "ok"


def test_report_direction_uses_metric_key_not_suite_label() -> None:
    baseline = {
        "benchmark_results": [
            {
                "metrics": [
                    {"name": "bench.latency.tokens_per_second", "value": 20.0},
                ]
            }
        ],
        "benchmark_context_rows": [
            {
                "suite": "latency",
                "context_length": 128,
                "generation_length": 32,
                "batch_size": 1,
                "speculative_acceptance_rate": 0.50,
            }
        ],
    }
    candidate = {
        "benchmark_results": [
            {
                "metrics": [
                    {"name": "bench.latency.tokens_per_second", "value": 25.0},
                ]
            }
        ],
        "benchmark_context_rows": [
            {
                "suite": "latency",
                "context_length": 128,
                "generation_length": 32,
                "batch_size": 1,
                "speculative_acceptance_rate": 0.70,
            }
        ],
    }

    report = build_benchmark_evaluation_report(baseline=baseline, candidate=candidate)

    rows_by_metric = {row["metric"]: row for row in report["rows"]}

    assert rows_by_metric["bench.latency.tokens_per_second"]["direction"] == "higher_is_better"
    assert rows_by_metric["bench.latency.tokens_per_second"]["status"] == "ok"
    assert (
        rows_by_metric[
            "bench.context.latency.ctx128.gen32.b1.speculative_acceptance_rate_mean"
        ]["direction"]
        == "higher_is_better"
    )
    assert (
        rows_by_metric[
            "bench.context.latency.ctx128.gen32.b1.speculative_acceptance_rate_mean"
        ]["status"]
        == "ok"
    )


def test_report_builder_aggregates_evaluation_sample_probes() -> None:
    baseline = {
        "evaluation_samples": [
            {
                "suite_id": "mmlu",
                "sample_render_ms": 10.0,
                "inference_ms": 100.0,
                "extraction_ms": 5.0,
                "validation_ms": 2.0,
                "scoring_ms": 1.0,
                "raw_response_chars": 20,
                "extracted_result_chars": 1,
                "failure_stage": "scoring",
            }
        ]
    }
    candidate = {
        "evaluation_samples": [
            {
                "suite_id": "mmlu",
                "sample_render_ms": 11.0,
                "inference_ms": 90.0,
                "extraction_ms": 5.0,
                "validation_ms": 2.0,
                "scoring_ms": 1.0,
                "raw_response_chars": 24,
                "extracted_result_chars": 1,
                "failure_stage": "scoring",
            },
            {
                "suite_id": "mmlu",
                "sample_render_ms": 13.0,
                "inference_ms": 110.0,
                "extraction_ms": 7.0,
                "validation_ms": 2.0,
                "scoring_ms": 2.0,
                "raw_response_chars": 30,
                "extracted_result_chars": 2,
                "failure_stage": "scoring",
            },
        ]
    }

    report = build_benchmark_evaluation_report(baseline=baseline, candidate=candidate)

    rows_by_metric = {row["metric"]: row for row in report["rows"]}

    assert rows_by_metric["eval.sample.mmlu.sample_render_ms_mean"]["status"] == "warning"
    assert rows_by_metric["eval.sample.mmlu.inference_ms_mean"]["status"] == "ok"
    assert rows_by_metric["eval.sample.mmlu.failure_stage.scoring.failure_count"]["status"] == (
        "warning"
    )


def test_report_builder_summarizes_run_evidence_probes_and_exports_probe_metrics() -> None:
    baseline = {
        "run_evidence": [
            _run_evidence(
                run_id="base-run",
                run_kind="serving_benchmark",
                decode_ms=10.0,
                status="completed",
            )
        ]
    }
    candidate = {
        "run_evidence": [
            _run_evidence(
                run_id="head-run",
                run_kind="serving_benchmark",
                decode_ms=20.0,
                status="failed",
                fallback_count=1,
                system_power_w=25.0,
                telemetry_failure_count=1,
            )
        ]
    }

    report = build_benchmark_evaluation_report(baseline=baseline, candidate=candidate)
    rows_by_metric = {row["metric"]: row for row in report["rows"]}

    assert rows_by_metric["probe.serving_benchmark.runtime.decode.duration_ms_mean"]["baseline"] == 10.0
    assert rows_by_metric["probe.serving_benchmark.runtime.decode.duration_ms_mean"]["candidate"] == 20.0
    assert rows_by_metric["probe.serving_benchmark.runtime.decode.failed_count"]["candidate"] == 1.0
    assert rows_by_metric["probe.serving_benchmark.runtime.fallback_enter.completed_count"]["candidate"] == 1.0
    assert rows_by_metric["telemetry.serving_benchmark.average_system_power_w_mean"]["candidate"] == 25.0
    assert rows_by_metric["telemetry.serving_benchmark.telemetry_failure_count"]["candidate"] == 1.0
    assert report["probe_summary"]["candidate"]["failed_phases"][0]["phase"] == "decode"
    report["probe_summary"]["baseline"] = []
    report["probe_summary"]["candidate"]["slowest_phases"].insert(0, "not-a-row")
    markdown = render_markdown_report(report)
    assert "## Probe Summary" in markdown
    assert "| runtime | decode | 20.0000 | failed |" in markdown


def test_report_builder_uses_aggregate_probe_metrics_not_sample_details() -> None:
    baseline = {
        "run_evidence": [
            _evaluation_run_evidence_with_sample_probes(
                run_id="base-eval",
                aggregate_decode_ms=100.0,
                detail_decode_ms=90.0,
                failed_count=2,
            )
        ]
    }
    candidate = {
        "run_evidence": [
            _evaluation_run_evidence_with_sample_probes(
                run_id="head-eval",
                aggregate_decode_ms=120.0,
                detail_decode_ms=110.0,
                failed_count=3,
            )
        ]
    }

    report = build_benchmark_evaluation_report(baseline=baseline, candidate=candidate)
    rows_by_metric = {row["metric"]: row for row in report["rows"]}

    assert rows_by_metric["probe.evaluation.runtime.decode.duration_ms_mean"]["baseline"] == 100.0
    assert rows_by_metric["probe.evaluation.runtime.decode.duration_ms_mean"]["candidate"] == 120.0
    assert rows_by_metric["probe.evaluation.worker.aggregate_result.failed_count"]["baseline"] == 2.0
    assert rows_by_metric["probe.evaluation.worker.aggregate_result.failed_count"]["candidate"] == 3.0
    assert rows_by_metric["probe.evaluation.runtime.fallback_enter.completed_count"]["candidate"] == 1.0


def test_report_builder_adds_contract_sections_from_run_evidence() -> None:
    report = build_benchmark_evaluation_report(
        baseline={
            "run_evidence": [
                _run_evidence(
                    run_id="base-run",
                    run_kind="serving_benchmark",
                    decode_ms=10.0,
                    status="completed",
                    system_power_w=15.0,
                )
            ]
        },
        candidate={
            "run_evidence": [
                _run_evidence(
                    run_id="head-run",
                    run_kind="serving_benchmark",
                    decode_ms=20.0,
                    status="failed",
                    fallback_count=1,
                    system_power_w=25.0,
                    telemetry_failure_count=1,
                )
            ]
        },
        report_kind="pr_evidence",
    )

    assert report["report_kind"] == "pr_evidence"
    assert report["source_evidence_ids"] == ["base-run", "head-run"]
    assert report["runs"][0]["trace_id"] == "base-run:trace"
    assert report["targets"][0]["target_model_id"] == "mlx-community/test-model"
    assert report["telemetry_summary"]["candidate"][0]["collector_status"] == "partial"
    assert report["model_memory_summary"]["candidate"][0]["runtime_model_handle"] == "head-run-model::1"
    assert report["model_memory_summary"]["candidate"][0]["runtime_stats_model_resident_bytes"] == 4096
    assert report["model_memory_summary"]["candidate"][0]["load_rss_delta_bytes"] == 5000
    assert report["process_attribution"]["candidate"][0]["primary_runtime_process"]["pid"] == 101
    assert report["comparison"]["comparison_validity"] == "valid"
    assert report["gate_result"]["overall_result"] == "fail"
    assert report["gate_result"]["required_telemetry_present"] is True
    assert report["gate_result"]["evidence_validity_metrics"]["required_evidence_present"] == 1.0
    assert report["gate_result"]["evidence_validity_metrics"]["required_probe_phases_present"] == 1.0
    assert report["gate_result"]["evidence_validity_metrics"]["required_telemetry_present"] == 1.0
    assert any(
        row["metric"] == "probe.serving_benchmark.runtime.decode.duration_ms_mean"
        and row["result"] == "fail"
        for row in report["metrics"]
    )
    assert_valid_report_payload(report)

    markdown = render_markdown_report(report)
    assert "## Report Identity" in markdown
    assert "## Gate Summary" in markdown
    assert "## Telemetry Summary" in markdown
    assert "## Model Memory Summary" in markdown
    assert "Registry Model Resident" in markdown
    assert "powermetrics_failed:fixture" in markdown


def test_model_memory_report_helpers_ignore_missing_or_nonnumeric_values() -> None:
    assert benchmark_evaluation_report._model_memory_csv_rows({}) == []
    assert benchmark_evaluation_report._render_model_memory_summary_markdown([]) == []

    report = build_benchmark_evaluation_report(
        baseline={
            "run_evidence": [
                {
                    **_run_evidence(
                        run_id="base-run",
                        run_kind="serving_benchmark",
                        decode_ms=10.0,
                        status="completed",
                    ),
                    "model_memory_summary": {"runtime_model_handle": "base::1", "bad": "not-a-number"},
                }
            ]
        },
        candidate={
            "run_evidence": [
                {
                    **_run_evidence(
                        run_id="head-run",
                        run_kind="serving_benchmark",
                        decode_ms=10.0,
                        status="completed",
                    ),
                    "model_memory_summary": {"runtime_model_handle": "head::1", "bad": "not-a-number"},
                }
            ]
        },
    )

    assert all("model_memory.serving_benchmark.bad_mean" != row["metric"] for row in report["metrics"])


def test_report_verifier_rejects_missing_required_sections() -> None:
    report = build_benchmark_evaluation_report(
        baseline={
            "run_evidence": [
                _run_evidence(
                    run_id="base-run",
                    run_kind="serving_benchmark",
                    decode_ms=10.0,
                    status="completed",
                )
            ]
        },
        candidate={
            "run_evidence": [
                _run_evidence(
                    run_id="head-run",
                    run_kind="serving_benchmark",
                    decode_ms=10.0,
                    status="completed",
                )
            ]
        },
    )
    malformed = dict(report)
    malformed.pop("report_id")
    malformed["targets"] = []
    malformed["metrics"] = []
    malformed["probe_summary"] = {"baseline": {"probe_count": 0}, "candidate": {"probe_count": 0}}
    malformed["telemetry_summary"] = {"baseline": [], "candidate": []}
    malformed["gate_result"] = {}

    errors = validate_report_payload(malformed)

    assert "missing required report identity field: report_id" in errors
    assert "targets must be a non-empty list" in errors
    assert "metrics must be a non-empty list" in errors
    assert "probe_summary.baseline.probe_count must be positive" in errors
    assert "telemetry_summary.candidate must be a non-empty list" in errors
    assert "gate_result.overall_result must be pass, fail, or informational" in errors


def test_report_gate_fails_missing_evidence_instead_of_downgrading_to_informational() -> None:
    report = build_benchmark_evaluation_report(baseline={}, candidate={})

    assert report["gate_result"]["overall_result"] == "fail"
    assert report["gate_result"]["required_evidence_present"] is False
    assert report["gate_result"]["required_probe_phases_present"] is False
    assert report["gate_result"]["required_telemetry_present"] is False
    assert {
        failure["metric"] for failure in report["gate_result"]["blocking_failures"]
    } == {
        "evidence.source_evidence_ids",
        "evidence.probe_timeline",
        "evidence.telemetry_summary",
    }
    assert report["gate_result"]["evidence_validity_metrics"] == {
        "source_evidence_count": 0,
        "required_evidence_present": 0.0,
        "required_probe_phases_present": 0.0,
        "required_telemetry_present": 0.0,
        "known_gap_count": 5.0,
        "blocking_failure_count": 3.0,
    }
    errors = validate_report_payload(report)
    assert "source_evidence_ids must be a non-empty list" in errors
    assert "probe_summary.baseline.probe_count must be positive" in errors
    assert "telemetry_summary.baseline must be a non-empty list" in errors


def test_report_verifier_reports_field_level_shape_errors() -> None:
    valid_report = build_benchmark_evaluation_report(
        baseline={
            "run_evidence": [
                _run_evidence(
                    run_id="base-run",
                    run_kind="serving_benchmark",
                    decode_ms=10.0,
                    status="completed",
                )
            ]
        },
        candidate={
            "run_evidence": [
                _run_evidence(
                    run_id="head-run",
                    run_kind="serving_benchmark",
                    decode_ms=10.0,
                    status="completed",
                )
            ]
        },
    )
    malformed = dict(valid_report)
    malformed["schema_version"] = "bad.schema"
    malformed["generator_name"] = ""
    malformed["source_evidence_ids"] = []
    malformed["runs"] = [
        "not-a-run",
        {"side": "baseline"},
        {**valid_report["runs"][0], "run_id": ""},
    ]
    malformed["targets"] = [
        "not-a-target",
        {"side": "baseline"},
        {**valid_report["targets"][0], "target_model_id": ""},
    ]
    malformed["metrics"] = [
        "not-a-metric",
        {**valid_report["metrics"][0], "metric": ""},
        {"metric": "missing.gate", "result": "bogus"},
    ]
    malformed["probe_summary"] = {"baseline": [], "candidate": {"probe_count": 0}}
    malformed["telemetry_summary"] = {
        "baseline": ["not-telemetry", {"collector_status": "", "telemetry_failures": "bad"}],
        "candidate": [{"collector_status": "collected"}],
    }
    malformed["gate_result"] = []

    errors = validate_report_payload(malformed)

    assert "schema_version must be melix.benchmark_evaluation_report.v1" in errors
    assert "required report identity field is empty: generator_name" in errors
    assert "source_evidence_ids must be a non-empty list" in errors
    assert "runs[0] must be an object" in errors
    assert "runs[1] missing required field: run_id" in errors
    assert "runs[2] required field is empty: run_id" in errors
    assert "targets[0] must be an object" in errors
    assert "targets[1] missing required field: run_id" in errors
    assert "targets[2] required field is empty: target_model_id" in errors
    assert "metrics[0] must be an object" in errors
    assert "metrics[1] missing metric name" in errors
    assert "metrics[2] missing gate_policy" in errors
    assert "metrics[2] result must be pass, fail, or informational" in errors
    assert "probe_summary.baseline must be an object" in errors
    assert "telemetry_summary.baseline[0] must be an object" in errors
    assert "telemetry_summary.baseline[1] missing collector_status" in errors
    assert "telemetry_summary.baseline[1] missing telemetry_failures" in errors
    assert "gate_result must be an object" in errors

    malformed_probe_root = dict(valid_report)
    malformed_probe_root["probe_summary"] = []
    malformed_probe_root["telemetry_summary"] = []
    assert "probe_summary must be an object" in validate_report_payload(malformed_probe_root)
    assert "telemetry_summary must be an object" in validate_report_payload(malformed_probe_root)

    with pytest.raises(ReportValidationError) as exc_info:
        assert_valid_report_payload(malformed)
    assert "schema_version must be melix.benchmark_evaluation_report.v1" in str(exc_info.value)


def test_report_verifier_rejects_failed_telemetry_encoded_as_zero() -> None:
    report = build_benchmark_evaluation_report(
        baseline={
            "run_evidence": [
                _run_evidence(
                    run_id="base-run",
                    run_kind="serving_benchmark",
                    decode_ms=10.0,
                    status="completed",
                    system_power_w=15.0,
                )
            ]
        },
        candidate={
            "run_evidence": [
                _run_evidence(
                    run_id="head-run",
                    run_kind="serving_benchmark",
                    decode_ms=10.0,
                    status="completed",
                    system_power_w=0.0,
                    telemetry_failure_count=1,
                )
            ]
        },
    )

    errors = validate_report_payload(report)

    assert (
        "telemetry_summary.candidate[0].average_system_power_w must not synthesize zero telemetry"
        in errors
    )


def test_report_private_helpers_cover_remaining_edge_branches() -> None:
    assert benchmark_evaluation_report._int_or_none(1.5) == 1
    assert benchmark_evaluation_report._int_or_none("2.0") == 2
    assert benchmark_evaluation_report._int_or_none("bad") is None
    assert benchmark_evaluation_report._int_or_none(None) is None


def test_metric_direction_fast_path_covers_report_probe_keys() -> None:
    expected = {
        "ttft_ms": "lower_is_better",
        "tokens_per_second": "higher_is_better",
        "request_latency_p95_ms": "lower_is_better",
        "tool_call_count_sum": "lower_is_better",
        "tool_latency_ms_mean": "lower_is_better",
        "observation_bytes_sum": "lower_is_better",
        "fatal_rate_rate": "lower_is_better",
        "turn_count_sum": "lower_is_better",
        "request_latency_ms_mean": "lower_is_better",
        "ttft_ms_mean": "lower_is_better",
        "duration_ms_mean": "lower_is_better",
        "prefill_tokens_per_second_mean": "higher_is_better",
        "decode_tokens_per_second_mean": "higher_is_better",
        "peak_memory_bytes_mean": "lower_is_better",
        "call_count_mean": "lower_is_better",
        "observation_count_mean": "lower_is_better",
        "completed_count_mean": "lower_is_better",
        "timeout_count_mean": "lower_is_better",
        "failed_count_mean": "lower_is_better",
        "latency_ms_mean": "lower_is_better",
        "observation_emitted_bytes_mean": "lower_is_better",
        "speculative_acceptance_rate_mean": "higher_is_better",
        "dflash_rollback_count_sum": "lower_is_better",
        "typed_score_mean": "higher_is_better",
        "raw_response_chars_mean": "neutral",
    }

    for metric_key, direction in expected.items():
        assert _METRIC_DIRECTION_BY_KEY[metric_key] == direction
        assert _metric_direction(f"bench.synthetic.{metric_key}") == direction


def test_report_builder_warns_on_agentic_tool_turn_cost_regressions() -> None:
    baseline = {
        "benchmark_context_rows": [
            {
                "suite": "agentic",
                "context_length": 128,
                "generation_length": 32,
                "batch_size": 1,
                "tool_call_count": 1,
                "tool_latency_ms": 5.0,
                "observation_bytes": 16,
                "fatal_rate": 0.0,
                "turn_count": 2,
                "agentic_tool_metrics": {
                    "agentic_tool.call_count": 1.0,
                    "agentic_tool.completed_count": 1.0,
                    "agentic_tool.timeout_count": 0.0,
                    "agentic_tool.failed_count": 0.0,
                    "agentic_tool.latency_ms": 5.0,
                    "agentic_tool.observation_emitted_bytes": 16.0,
                },
            }
        ]
    }
    candidate = {
        "benchmark_context_rows": [
            {
                "suite": "agentic",
                "context_length": 128,
                "generation_length": 32,
                "batch_size": 1,
                "tool_call_count": 2,
                "tool_latency_ms": 9.0,
                "observation_bytes": 64,
                "fatal_rate": 1.0,
                "turn_count": 4,
                "agentic_tool_metrics": {
                    "agentic_tool.call_count": 2.0,
                    "agentic_tool.completed_count": 2.0,
                    "agentic_tool.timeout_count": 1.0,
                    "agentic_tool.failed_count": 1.0,
                    "agentic_tool.latency_ms": 9.0,
                    "agentic_tool.observation_emitted_bytes": 64.0,
                },
            }
        ]
    }

    report = build_benchmark_evaluation_report(baseline=baseline, candidate=candidate)

    rows_by_metric = {row["metric"]: row for row in report["rows"]}
    label = "bench.context.agentic.ctx128.gen32.b1"
    expected_warning_metrics = (
        f"{label}.tool_call_count_sum",
        f"{label}.tool_latency_ms_mean",
        f"{label}.observation_bytes_sum",
        f"{label}.fatal_rate_rate",
        f"{label}.turn_count_sum",
        f"{label}.agentic_tool.call_count_mean",
        f"{label}.agentic_tool.completed_count_mean",
        f"{label}.agentic_tool.timeout_count_mean",
        f"{label}.agentic_tool.failed_count_mean",
        f"{label}.agentic_tool.latency_ms_mean",
        f"{label}.agentic_tool.observation_emitted_bytes_mean",
    )

    for metric in expected_warning_metrics:
        row = rows_by_metric[metric]
        assert row["direction"] == "lower_is_better"
        assert row["status"] == "warning"


def test_report_builder_aggregates_numeric_probe_values_without_normalizing_all_values() -> None:
    report = build_benchmark_evaluation_report(
        baseline={
            "benchmark_context_rows": [
                {
                    "suite": "mixed",
                    "context_length": 128,
                    "generation_length": 32,
                    "batch_size": 1,
                    "prefill_ms": 7,
                    "cache_hit": True,
                },
                {
                    "suite": "mixed",
                    "context_length": 128,
                    "generation_length": 32,
                    "batch_size": 1,
                    "prefill_ms": "9.0",
                    "cache_hit": False,
                },
            ]
        },
        candidate={
            "benchmark_context_rows": [
                {
                    "suite": "mixed",
                    "context_length": 128,
                    "generation_length": 32,
                    "batch_size": 1,
                    "prefill_ms": 8.0,
                    "cache_hit": True,
                },
                {
                    "suite": "mixed",
                    "context_length": 128,
                    "generation_length": 32,
                    "batch_size": 1,
                    "prefill_ms": "10.0",
                    "cache_hit": True,
                },
            ]
        },
    )

    rows_by_metric = {row["metric"]: row for row in report["rows"]}

    assert rows_by_metric["bench.context.mixed.ctx128.gen32.b1.prefill_ms_mean"]["baseline"] == (
        pytest.approx(8.0)
    )
    assert rows_by_metric["bench.context.mixed.ctx128.gen32.b1.prefill_ms_mean"]["candidate"] == (
        pytest.approx(9.0)
    )
    assert rows_by_metric["bench.context.mixed.ctx128.gen32.b1.cache_hit_rate"]["baseline"] == (
        pytest.approx(0.5)
    )
    assert rows_by_metric["bench.context.mixed.ctx128.gen32.b1.cache_hit_rate"]["candidate"] == (
        pytest.approx(1.0)
    )


def test_label_part_preserves_numeric_labels_and_normalizes_text_spaces() -> None:
    assert _label_part(1024) == "1024"
    assert _label_part(1.5) == "1.5"
    assert _label_part(True) == "True"
    assert _label_part("long suite") == "long_suite"


def test_benchmark_probe_label_reuses_cached_matrix_labels() -> None:
    cache: dict[tuple[object, object, object, object, object], str] = {}
    row = {
        "suite_id": "smoke",
        "context_length": 128,
        "generation_length": 32,
        "batch_size": 1,
        "concurrency_level": 2,
    }

    first = _benchmark_probe_label(row, matrix_label_cache=cache)
    second = _benchmark_probe_label(dict(row), matrix_label_cache=cache)

    assert first == "smoke.ctx128.gen32.b1.c2"
    assert second == first
    assert cache == {("smoke", 128, 32, 1, 2): first}


def test_report_builder_uses_sparse_benchmark_probe_rows_without_fixed_key_scans() -> None:
    sparse_row = _SparseProbeRow(
        {
            "suite": "smoke",
            "context_length": 128,
            "generation_length": 32,
            "batch_size": 1,
            "prefill_ms": 7.0,
            "ignored": 999,
            "prefill_ms_extra": 123,
        },
        forbidden_keys={"prefill_ms", "decode_ms", "tokens_in", "dflash_enabled"},
        forbid_contains=True,
    )

    report = build_benchmark_evaluation_report(
        baseline={"benchmark_context_rows": [sparse_row]},
        candidate={"benchmark_context_rows": [dict(sparse_row)]},
    )

    rows_by_metric = {row["metric"]: row for row in report["rows"]}

    assert set(rows_by_metric) == {"bench.context.smoke.ctx128.gen32.b1.prefill_ms_mean"}
    assert rows_by_metric["bench.context.smoke.ctx128.gen32.b1.prefill_ms_mean"]["baseline"] == (
        pytest.approx(7.0)
    )
    assert rows_by_metric["bench.context.smoke.ctx128.gen32.b1.prefill_ms_mean"]["status"] == "ok"


def test_report_builder_uses_sparse_evaluation_sample_rows_without_fixed_key_scans() -> None:
    sparse_row = _SparseProbeRow(
        {
            "suite_id": "mmlu",
            "sample_render_ms": 5.0,
            "failure_stage": "validation",
            "ignored": 42,
            "sample_render_ms_extra": 77,
        },
        forbidden_keys={
            "sample_render_ms",
            "inference_ms",
            "raw_response_chars",
            "extracted_result_chars",
        },
    )

    report = build_benchmark_evaluation_report(
        baseline={"evaluation_samples": [sparse_row]},
        candidate={"evaluation_samples": [dict(sparse_row)]},
    )

    rows_by_metric = {row["metric"]: row for row in report["rows"]}

    assert set(rows_by_metric) == {
        "eval.sample.mmlu.failure_stage.validation.failure_count",
        "eval.sample.mmlu.sample_render_ms_mean",
    }
    assert rows_by_metric["eval.sample.mmlu.sample_render_ms_mean"]["candidate"] == pytest.approx(5.0)
    assert rows_by_metric["eval.sample.mmlu.sample_render_ms_mean"]["status"] == "ok"
    assert rows_by_metric["eval.sample.mmlu.failure_stage.validation.failure_count"]["status"] == "ok"


def test_report_renderers_are_stable_and_sticky_comment_is_marked() -> None:
    report = build_benchmark_evaluation_report(
        baseline=_bundle(ttft_ms=100.0, tokens_per_second=50.0, accuracy=0.8),
        candidate=_bundle(ttft_ms=95.0, tokens_per_second=55.0, accuracy=0.82),
    )

    terminal = render_terminal_report(report)
    markdown = render_markdown_report(report)
    comment = build_sticky_comment_body(markdown)

    assert "Metric" in terminal
    assert "bench.smoke.ttft_ms" in terminal
    assert "| Metric | Baseline | Candidate | Delta | Status |" in markdown
    assert "<!-- melix-benchmark-evaluation-report -->" in comment
    assert comment.endswith("\n")


def test_report_warns_when_evaluation_schema_or_hints_hashes_differ() -> None:
    baseline = {
        "evaluation_jobs": [
            {
                "job_id": "eval-baseline",
                "parameters": {
                    "schema_sha256": "schema-a",
                    "hints_sha256": "hints-a",
                },
            }
        ]
    }
    candidate = {
        "evaluation_jobs": [
            {
                "job_id": "eval-candidate",
                "parameters": {
                    "schema_sha256": "schema-b",
                    "hints_sha256": "hints-b",
                },
            }
        ]
    }

    report = build_benchmark_evaluation_report(
        baseline=baseline,
        candidate=candidate,
    )
    markdown = render_markdown_report(report)

    assert report["summary"]["status"] == "warning"
    assert report["summary"]["warning_count"] == 2
    assert report["comparison"]["comparison_validity"] == "partial"
    assert report["reproducibility_warnings"] == [
        "evaluation_schema_sha256_mismatch:baseline=schema-a;candidate=schema-b",
        "evaluation_hints_sha256_mismatch:baseline=hints-a;candidate=hints-b",
    ]
    assert report["non_blocking_warnings"] == report["reproducibility_warnings"]
    assert "## Reproducibility Warnings" in markdown
    assert "evaluation_schema_sha256_mismatch" in markdown
    assert "evaluation_hints_sha256_mismatch" in markdown


def test_report_accepts_matching_reproducibility_hashes_and_run_evidence_metadata() -> None:
    matching = {
        "evaluation_jobs": [
            {
                "job_id": "eval-a",
                "parameters": {
                    "schema_sha256": "schema-a",
                    "hints_sha256": "hints-a",
                },
            }
        ]
    }
    matching_report = build_benchmark_evaluation_report(
        baseline=matching,
        candidate=matching,
    )

    assert matching_report["reproducibility_warnings"] == []
    assert matching_report["summary"]["warning_count"] == 0

    missing_candidate_report = build_benchmark_evaluation_report(
        baseline={
            "evaluation_jobs": [{"job_id": "legacy", "parameters": "legacy"}],
            "run_evidence": [
                {"run_id": "bad-domain", "domain_results": {"evaluation": "legacy"}},
                {
                    "run_id": "evidence-eval",
                    "domain_results": {
                        "evaluation": {
                            "job": {
                                "parameters": {
                                    "schema_sha256": "schema-from-evidence",
                                }
                            }
                        }
                    },
                },
            ],
        },
        candidate={},
    )

    assert missing_candidate_report["reproducibility_warnings"] == [
        "evaluation_schema_sha256_mismatch:baseline=schema-from-evidence;candidate=missing"
    ]
    assert missing_candidate_report["summary"]["warning_count"] == 1


def test_markdown_cell_escapes_table_control_characters() -> None:
    assert _markdown_cell("model`a|b\nc") == "model\\`a\\|b c"


def test_report_loader_rejects_malformed_inputs(tmp_path: Path) -> None:
    malformed = tmp_path / "bad.json"
    malformed.write_text("{", encoding="utf-8")

    with pytest.raises(ValueError, match="could not be decoded"):
        load_report_input(malformed)


def test_report_loader_rejects_missing_and_non_object_inputs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="is missing"):
        load_report_input(tmp_path / "missing")

    non_object = tmp_path / "array.json"
    non_object.write_text("[]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must be a JSON object"):
        load_report_input(non_object)


def test_report_loader_accepts_export_bundle_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(
        json.dumps(_bundle(ttft_ms=100.0, tokens_per_second=50.0, accuracy=0.8)) + "\n",
        encoding="utf-8",
    )

    def forbid_read_text(self: Path, *args: object, **kwargs: object) -> str:
        del self, args, kwargs
        raise AssertionError("load_report_input should decode JSON from bytes")

    monkeypatch.setattr(Path, "read_text", forbid_read_text)

    payload = load_report_input(bundle_path)

    assert payload["export_schema_version"] == "melix.benchmark_export.v1"


def test_report_loader_accepts_export_bundle_directory_fallback(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "artifact"
    bundle_dir.mkdir()
    (bundle_dir / "export-bundle.json").write_text(
        json.dumps(_bundle(ttft_ms=100.0, tokens_per_second=50.0, accuracy=0.8)) + "\n",
        encoding="utf-8",
    )

    payload = load_report_input(bundle_dir)

    assert payload["export_schema_version"] == "melix.benchmark_export.v1"


def test_neutral_direction_ok_when_equal_not_comparable_when_changed() -> None:
    baseline = {
        "benchmark_context_rows": [
            {
                "suite": "smoke",
                "context_length": 2,
                "generation_length": 8,
                "batch_size": 1,
                "tokens_in": 2,
                "tokens_out": 1,
                "first_token_index": 1,
                "dflash_block_size": 0,
                "dflash_enabled": False,
                "dflash_target_hidden_layers": 0,
                "speculative_draft_model_configured": False,
                "speculative_num_draft_tokens": 0,
            }
        ]
    }
    # Candidate identical to baseline — every neutral metric should be ok
    report_equal = build_benchmark_evaluation_report(baseline=baseline, candidate=baseline)
    rows = {row["metric"]: row for row in report_equal["rows"]}
    label = "bench.context.smoke.ctx2.gen8.b1"
    assert rows[f"{label}.tokens_in_mean"]["status"] == "ok"
    assert rows[f"{label}.tokens_out_mean"]["status"] == "ok"
    assert rows[f"{label}.first_token_index_mean"]["status"] == "ok"
    assert rows[f"{label}.dflash_block_size_mean"]["status"] == "ok"
    assert rows[f"{label}.dflash_enabled_rate"]["status"] == "ok"
    assert rows[f"{label}.dflash_target_hidden_layers_mean"]["status"] == "ok"
    assert rows[f"{label}.speculative_draft_model_configured_rate"]["status"] == "ok"
    assert rows[f"{label}.speculative_num_draft_tokens_mean"]["status"] == "ok"
    assert report_equal["summary"]["not_comparable_count"] == 0

    # Candidate with changed neutral metric — should be not_comparable
    candidate_changed = {
        "benchmark_context_rows": [
            {
                "suite": "smoke",
                "context_length": 2,
                "generation_length": 8,
                "batch_size": 1,
                "tokens_in": 4,
                "tokens_out": 1,
                "first_token_index": 1,
                "dflash_block_size": 0,
                "dflash_enabled": False,
                "dflash_target_hidden_layers": 0,
                "speculative_draft_model_configured": False,
                "speculative_num_draft_tokens": 0,
            }
        ]
    }
    report_changed = build_benchmark_evaluation_report(baseline=baseline, candidate=candidate_changed)
    rows_changed = {row["metric"]: row for row in report_changed["rows"]}
    assert rows_changed[f"{label}.tokens_in_mean"]["status"] == "not_comparable"
    assert report_changed["summary"]["not_comparable_count"] == 1


def test_eval_sample_neutral_metrics_ok_when_equal_not_comparable_when_changed() -> None:
    baseline = {
        "evaluation_samples": [
            {
                "suite_id": "mmlu",
                "inference_ms": 10.0,
                "extraction_ms": 5.0,
                "validation_ms": 2.0,
                "scoring_ms": 1.0,
                "raw_response_chars": 1,
                "extracted_result_chars": 1,
            }
        ]
    }
    # Identical candidate — neutral eval-sample metrics should be ok
    report_equal = build_benchmark_evaluation_report(baseline=baseline, candidate=baseline)
    rows = {row["metric"]: row for row in report_equal["rows"]}
    assert rows["eval.sample.mmlu.raw_response_chars_mean"]["status"] == "ok"
    assert rows["eval.sample.mmlu.extracted_result_chars_mean"]["status"] == "ok"
    assert report_equal["summary"]["not_comparable_count"] == 0

    # Candidate with changed neutral metric — should be not_comparable
    candidate_changed = {
        "evaluation_samples": [
            {
                "suite_id": "mmlu",
                "inference_ms": 10.0,
                "extraction_ms": 5.0,
                "validation_ms": 2.0,
                "scoring_ms": 1.0,
                "raw_response_chars": 3,
                "extracted_result_chars": 1,
            }
        ]
    }
    report_changed = build_benchmark_evaluation_report(baseline=baseline, candidate=candidate_changed)
    rows_changed = {row["metric"]: row for row in report_changed["rows"]}
    assert rows_changed["eval.sample.mmlu.raw_response_chars_mean"]["status"] == "not_comparable"
    assert rows_changed["eval.sample.mmlu.extracted_result_chars_mean"]["status"] == "ok"
    assert report_changed["summary"]["not_comparable_count"] == 1


def test_write_report_outputs_writes_json_and_markdown(tmp_path: Path) -> None:
    report = build_benchmark_evaluation_report(
        baseline={
            **_bundle(ttft_ms=100.0, tokens_per_second=50.0, accuracy=0.8),
            "run_evidence": [
                _run_evidence(
                    run_id="base-run",
                    run_kind="serving_benchmark",
                    decode_ms=10.0,
                    status="completed",
                )
            ],
        },
        candidate={
            **_bundle(ttft_ms=95.0, tokens_per_second=55.0, accuracy=0.82),
            "run_evidence": [
                _run_evidence(
                    run_id="head-run",
                    run_kind="serving_benchmark",
                    decode_ms=8.0,
                    status="completed",
                )
            ],
        },
    )

    outputs = write_report_outputs(report=report, output_dir=tmp_path / "report")

    report_json = json.loads(outputs["json"].read_text(encoding="utf-8"))
    assert report_json["schema_version"] == "melix.benchmark_evaluation_report.v1"
    assert report_json["artifacts"]["csv_export_paths"]["metrics"].endswith("metrics.csv")
    assert "| Metric | Baseline | Candidate | Delta | Status |" in outputs["markdown"].read_text(
        encoding="utf-8"
    )
    assert outputs["csv_dir"].is_dir()
    assert outputs["runs_csv"].read_text(encoding="utf-8").splitlines()[0].startswith(
        "side,run_id,trace_id"
    )
    assert "bench.smoke.ttft_ms" in outputs["metrics_csv"].read_text(encoding="utf-8")
    assert "slowest_phases" in outputs["probe_phases_csv"].read_text(encoding="utf-8")
    assert "average_system_power_w" in outputs["telemetry_summary_csv"].read_text(
        encoding="utf-8"
    )
    assert "runtime_stats_model_resident_bytes" in outputs["model_memory_csv"].read_text(
        encoding="utf-8"
    )
    assert "## Model Memory Summary" in outputs["markdown"].read_text(encoding="utf-8")
    assert "primary_runtime_process" in outputs["processes_csv"].read_text(encoding="utf-8")
    assert "overall_result" not in outputs["gate_results_csv"].read_text(encoding="utf-8")
    assert "telemetry" in outputs["comparison_deltas_csv"].read_text(encoding="utf-8")
