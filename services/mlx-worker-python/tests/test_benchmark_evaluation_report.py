from __future__ import annotations

import json
from pathlib import Path

import pytest

from worker.productization.benchmark_evaluation_report import (
    build_benchmark_evaluation_report,
    build_sticky_comment_body,
    load_report_input,
    render_markdown_report,
    render_terminal_report,
)


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
    assert rows_by_metric[f"{label}.dflash_enabled_rate"]["status"] == "not_comparable"
    assert report["summary"]["warning_count"] == 3


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


def test_report_loader_rejects_malformed_inputs(tmp_path: Path) -> None:
    malformed = tmp_path / "bad.json"
    malformed.write_text("{", encoding="utf-8")

    with pytest.raises(ValueError, match="could not be decoded"):
        load_report_input(malformed)


def test_report_loader_accepts_export_bundle_path(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(
        json.dumps(_bundle(ttft_ms=100.0, tokens_per_second=50.0, accuracy=0.8)) + "\n",
        encoding="utf-8",
    )

    payload = load_report_input(bundle_path)

    assert payload["export_schema_version"] == "melix.benchmark_export.v1"
