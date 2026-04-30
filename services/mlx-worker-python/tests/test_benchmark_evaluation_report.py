from __future__ import annotations

import json
from pathlib import Path

import pytest

from worker.productization.benchmark_evaluation_report import (
    _aggregate_probe_values,
    _finalize_numeric_aggregate,
    _markdown_cell,
    _update_numeric_aggregate,
    build_benchmark_evaluation_report,
    build_sticky_comment_body,
    load_report_input,
    render_markdown_report,
    render_terminal_report,
    write_report_outputs,
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


def test_aggregate_probe_values_handles_empty_inputs() -> None:
    assert _aggregate_probe_values("prefill_ms", []) == ("mean", 0.0)
    assert _aggregate_probe_values("cache_hit", []) == ("rate", 0.0)
    assert _aggregate_probe_values("speculative_fallback_count", []) == ("sum", 0.0)


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
