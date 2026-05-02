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
    _label_part,
    _markdown_cell,
    _metric_direction,
    _metric_key_direction,
    _report_rows,
    _update_numeric_aggregate,
    _update_probe_aggregates_by_label,
    build_benchmark_evaluation_report,
    build_sticky_comment_body,
    load_report_input,
    render_markdown_report,
    render_terminal_report,
    write_report_outputs,
)


class _SparseProbeRow(dict[str, object]):
    def __init__(self, *args: object, forbidden_keys: set[str], **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._forbidden_keys = forbidden_keys

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

    metrics: dict[str, object] = {}
    _collect_benchmark_probe_metrics(metrics, [row_a, row_b], prefix="bench")

    label = "smoke.ctx1024.gen128.b1.c1"
    assert metrics == {
        f"bench.{label}.prefill_ms_mean": 12.0,
        f"bench.{label}.decode_ms_mean": 22.0,
        f"bench.{label}.speculative_fallback_count_sum": 4.0,
    }


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


def test_probe_collectors_use_registered_probe_key_order_without_items_scan() -> None:
    class NoItemsDict(dict[str, object]):
        def items(self):  # type: ignore[override]
            raise AssertionError("collector should scan registered probe keys directly")

    benchmark_metrics: dict[str, object] = {}
    _collect_benchmark_probe_metrics(
        benchmark_metrics,
        [
            NoItemsDict(
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
        label_cache: dict[tuple[str, str, str, str, str, str], str] | None = None,
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
    built_keys: list[tuple[str, str, str, str, str, str]] = []

    def tracked(key: tuple[str, str, str, str, str, str]) -> str:
        built_keys.append(key)
        return original(key)

    monkeypatch.setattr(benchmark_evaluation_report, "_build_benchmark_label", tracked)

    cache: dict[tuple[str, str, str, str, str, str], str] = {}
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
        ("bench", "smoke suite", "128", "32", "1", ""),
        ("matrix", "smoke suite", "128", "32", "1", "2"),
    ]


def test_benchmark_probe_label_cache_preserves_stringified_shape_boundaries() -> None:
    cache: dict[tuple[str, str, str, str, str, str], str] = {}

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


def test_metric_direction_fast_path_covers_report_probe_keys() -> None:
    expected = {
        "ttft_ms": "lower_is_better",
        "tokens_per_second": "higher_is_better",
        "request_latency_p95_ms": "lower_is_better",
        "speculative_acceptance_rate_mean": "higher_is_better",
        "dflash_rollback_count_sum": "lower_is_better",
        "typed_score_mean": "higher_is_better",
        "raw_response_chars_mean": "neutral",
    }

    for metric_key, direction in expected.items():
        assert _METRIC_DIRECTION_BY_KEY[metric_key] == direction
        assert _metric_direction(f"bench.synthetic.{metric_key}") == direction


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


def test_report_loader_accepts_export_bundle_path(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(
        json.dumps(_bundle(ttft_ms=100.0, tokens_per_second=50.0, accuracy=0.8)) + "\n",
        encoding="utf-8",
    )

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
        baseline=_bundle(ttft_ms=100.0, tokens_per_second=50.0, accuracy=0.8),
        candidate=_bundle(ttft_ms=95.0, tokens_per_second=55.0, accuracy=0.82),
    )

    outputs = write_report_outputs(report=report, output_dir=tmp_path / "report")

    assert json.loads(outputs["json"].read_text(encoding="utf-8"))["schema_version"] == (
        "melix.benchmark_evaluation_report.v1"
    )
    assert "| Metric | Baseline | Candidate | Delta | Status |" in outputs["markdown"].read_text(
        encoding="utf-8"
    )
