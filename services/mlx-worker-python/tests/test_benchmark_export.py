from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest

from worker.productization.benchmark_export import (
    _collect_benchmark_run,
    _collect_evaluation_run,
    _iter_jsonl_dict_rows,
    _iter_sorted_child_directories,
    _iter_sorted_matching_files,
    _load_json_object,
    _rows_to_csv,
    build_comparison_table,
    build_benchmark_batch_csv,
    build_benchmark_context_csv,
    build_benchmark_matrix_requests_csv,
    build_benchmark_matrix_summary_csv,
    build_evaluation_compare_samples_csv,
    build_evaluation_compare_summary_csv,
    build_benchmark_summary_csv,
    build_evaluation_samples_csv,
    build_evaluation_summary_csv,
    build_export_bundle,
    collect_benchmark_artifacts,
    collect_evaluation_artifacts,
    write_export_bundle,
)


class _CountingMetricList(list[dict[str, float | str]]):
    def __init__(self, items: list[dict[str, float | str]]) -> None:
        super().__init__(items)
        self.iteration_count = 0

    def __iter__(self):
        self.iteration_count += 1
        return super().__iter__()


def _write_bench_fixtures(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "bench-summary.json").write_text(
        json.dumps({
            "schema_version": "melix.serving_benchmark_job.v1",
            "job_id": "bench-1",
            "model_id": "melix-dev-text",
            "task_kind": "text-generation",
            "source_repo": "HuggingFaceH4/ultrachat_200k",
            "suites": ["smoke"],
            "context_lengths": [32],
            "generation_length": 8,
            "batch_sizes": [1],
            "repeats": 1,
            "cache_profile": "cold",
            "reasoning_mode": "",
            "structured_output_mode": "",
            "request_p50_ms": 24.45,
            "request_p95_ms": 24.45,
            "parameters": {},
            "status": "completed",
            "output_dir": str(root),
            "created_at_unix_ms": 101,
            "updated_at_unix_ms": 202,
        }) + "\n"
    )
    (root / "bench-context-rows.jsonl").write_text(
        json.dumps({
            "schema_version": "melix.serving_benchmark_context_row.v1",
            "job_id": "bench-1",
            "model_id": "melix-dev-text",
            "task_kind": "text-generation",
            "source_repo": "HuggingFaceH4/ultrachat_200k",
            "suite": "smoke",
            "context_length": 32,
            "generation_length": 8,
            "batch_size": 1,
            "repeat_index": 0,
            "prefill_tokens_per_second": 24.45,
            "decode_tokens_per_second": 47.08,
            "ttft_ms": 24.45,
            "request_latency_ms": 24.45,
            "peak_memory_bytes": 2048.0,
            "speedup_vs_batch_1": 1.0,
            "cache_profile": "cold",
            "reasoning_mode": "",
            "structured_output_mode": "",
        }) + "\n"
    )
    (root / "bench-batch-rows.jsonl").write_text(
        json.dumps({
            "schema_version": "melix.serving_benchmark_batch_row.v1",
            "job_id": "bench-1",
            "model_id": "melix-dev-text",
            "task_kind": "text-generation",
            "source_repo": "HuggingFaceH4/ultrachat_200k",
            "suite": "smoke",
            "context_length": 32,
            "generation_length": 8,
            "batch_size": 1,
            "repeat_index": 0,
            "prefill_tokens_per_second": 24.45,
            "decode_tokens_per_second": 47.08,
            "ttft_ms": 24.45,
            "request_latency_ms": 24.45,
            "peak_memory_bytes": 2048.0,
            "speedup_vs_batch_1": 1.0,
            "cache_profile": "cold",
            "reasoning_mode": "",
            "structured_output_mode": "",
        }) + "\n"
    )
    (root / "bench-result-smoke.json").write_text(
        json.dumps({
            "schema_version": "melix.serving_benchmark_result.v1",
            "job_id": "bench-1",
            "suite": "smoke",
            "metrics": [
                {"name": "bench.smoke.ttft_ms", "value": 24.45, "unit": "ms"},
                {"name": "bench.smoke.tokens_per_second", "value": 47.08, "unit": "tok/s"},
            ],
        }) + "\n"
    )


def _write_bench_run_fixture(root: Path, *, job_id: str, model_id: str, ttft_ms: float) -> None:
    run_root = root / "runs" / job_id
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "bench-summary.json").write_text(
        json.dumps({
            "schema_version": "melix.serving_benchmark_job.v1",
            "job_id": job_id,
            "model_id": model_id,
            "task_kind": "text-generation",
            "source_repo": "HuggingFaceH4/ultrachat_200k",
            "suites": ["smoke"],
            "context_lengths": [32],
            "generation_length": 8,
            "batch_sizes": [1],
            "repeats": 1,
            "cache_profile": "cold",
            "reasoning_mode": "",
            "structured_output_mode": "",
            "request_p50_ms": ttft_ms,
            "request_p95_ms": ttft_ms,
            "parameters": {"sample_size": "4"},
            "status": "completed",
            "output_dir": str(run_root),
            "created_at_unix_ms": 101,
            "updated_at_unix_ms": 202,
        }) + "\n"
    )
    (run_root / "bench-context-rows.jsonl").write_text(
        json.dumps({
            "schema_version": "melix.serving_benchmark_context_row.v1",
            "job_id": job_id,
            "model_id": model_id,
            "task_kind": "text-generation",
            "source_repo": "HuggingFaceH4/ultrachat_200k",
            "suite": "smoke",
            "context_length": 32,
            "generation_length": 8,
            "batch_size": 1,
            "repeat_index": 0,
            "prefill_tokens_per_second": 24.45,
            "decode_tokens_per_second": 47.08,
            "ttft_ms": ttft_ms,
            "request_latency_ms": ttft_ms,
            "peak_memory_bytes": 2048.0,
            "speedup_vs_batch_1": 1.0,
            "cache_profile": "cold",
            "reasoning_mode": "",
            "structured_output_mode": "",
        }) + "\n"
    )
    (run_root / "bench-batch-rows.jsonl").write_text(
        json.dumps({
            "schema_version": "melix.serving_benchmark_batch_row.v1",
            "job_id": job_id,
            "model_id": model_id,
            "task_kind": "text-generation",
            "source_repo": "HuggingFaceH4/ultrachat_200k",
            "suite": "smoke",
            "context_length": 32,
            "generation_length": 8,
            "batch_size": 1,
            "repeat_index": 0,
            "prefill_tokens_per_second": 24.45,
            "decode_tokens_per_second": 47.08,
            "ttft_ms": ttft_ms,
            "request_latency_ms": ttft_ms,
            "peak_memory_bytes": 2048.0,
            "speedup_vs_batch_1": 1.0,
            "cache_profile": "cold",
            "reasoning_mode": "",
            "structured_output_mode": "",
        }) + "\n"
    )
    (run_root / "bench-result-smoke.json").write_text(
        json.dumps({
            "schema_version": "melix.serving_benchmark_result.v1",
            "job_id": job_id,
            "suite": "smoke",
            "metrics": [
                {"name": "bench.smoke.ttft_ms", "value": ttft_ms, "unit": "ms"},
            ],
            "report_path": str(run_root / "bench-report.md"),
            "report_markdown": "# Melix Bench\n",
        }) + "\n"
    )


def _write_bench_matrix_run_fixture(root: Path, *, job_id: str) -> None:
    run_root = root / "matrix-runs" / job_id
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "bench-matrix-job.json").write_text(
        json.dumps({
            "schema_version": "melix.benchmark_matrix_job.v1",
            "job_id": job_id,
            "model_id": "melix-dev-text",
            "task_kind": "text-generation",
            "source_repo": "HuggingFaceH4/ultrachat_200k",
            "suite_ids": ["smoke"],
            "benchmark_mode": "matrix",
            "status": "completed",
            "output_dir": str(run_root),
            "created_at_unix_ms": 111,
            "updated_at_unix_ms": 222,
        }) + "\n"
    )
    (run_root / "bench-matrix-summary.jsonl").write_text(
        json.dumps({
            "job_id": job_id,
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
            "peak_memory_bytes_max": 2147483648,
            "queue_wait_mean_ms": 5.1,
            "queue_wait_p95_ms": 9.2,
            "created_at_unix_ms": 111,
        }) + "\n"
    )
    (run_root / "bench-matrix-requests.jsonl").write_text(
        json.dumps({
            "job_id": job_id,
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
            "peak_memory_bytes": 2147483648,
            "status": "completed",
            "error_code": "",
            "created_at_unix_ms": 111,
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
            "sample_size": 8,
            "output_dir": str(root),
            "created_at_unix_ms": 101,
            "updated_at_unix_ms": 202,
        }) + "\n"
    )
    (root / "evaluation-result.json").write_text(
        json.dumps({
            "schema_version": "melix.evaluation_result.v2",
            "job_id": "eval-1",
            "suite_id": "mmlu",
            "dataset_id": "mmlu.dev.v1",
            "sample_size": 8,
            "primary_score_name": "typed_score_mean",
            "primary_score_value": 0.75,
            "extraction_success_count": 8,
            "validation_success_count": 8,
            "scored_sample_count": 8,
            "failure_count": 0,
            "duration_seconds": 1.25,
            "metrics": [
                {"name": "eval.mmlu.typed_score_mean", "value": 0.75, "unit": "ratio"},
            ],
            "report_path": str(root / "evaluation-result.json"),
        }) + "\n"
    )
    (root / "evaluation-samples.jsonl").write_text(
        "\n".join([
            json.dumps({
                "schema_version": "melix.evaluation_sample.v2",
                "job_id": "eval-1",
                "suite_id": "mmlu",
                "dataset_id": "mmlu.dev.v1",
                "sample_id": "1",
                "system": "",
                "input_text": "2+2?",
                "target": "4",
                "raw_response": "4",
                "extracted_result": "4",
                "typed_score": 1.0,
                "time_s": 0.01,
                "extraction_status": "extracted",
                "validation_status": "validated",
                "failure_reason": "",
            }),
        ]) + "\n"
    )


def _write_eval_compare_fixtures(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "evaluation-compare-job.json").write_text(
        json.dumps({
            "schema_version": "melix.evaluation_compare_job.v2",
            "job_id": "eval-compare-1",
            "base_model_id": "melix-dev-text",
            "target_model_ids": ["melix-dev-text-lora-a"],
            "task_kind": "text-generation",
            "source_repo": "HuggingFaceH4/ultrachat_200k",
            "suite_id": "mmlu",
            "dataset_id": "mmlu.dev.v1",
            "sample_size": 8,
            "scoring_mode": "normalized_exact_match",
            "parameters": {
                "compare_mode": "base_vs_targets",
                "compare_target_model_ids": "melix-dev-text-lora-a",
            },
            "status": "completed",
            "output_dir": str(root),
            "created_at_unix_ms": 303,
            "updated_at_unix_ms": 404,
        }) + "\n"
    )
    (root / "evaluation-compare-summary.json").write_text(
        json.dumps({
            "schema_version": "melix.evaluation_compare_summary_bundle.v1",
            "job_id": "eval-compare-1",
            "base_model_id": "melix-dev-text",
            "suite_id": "mmlu",
            "dataset_id": "mmlu.dev.v1",
            "sample_size": 8,
            "created_at_unix_ms": 303,
            "target_summaries": [
                {
                    "schema_version": "melix.evaluation_compare_summary.v2",
                    "job_id": "eval-compare-1",
                    "base_model_id": "melix-dev-text",
                    "target_model_id": "melix-dev-text-lora-a",
                    "suite_id": "mmlu",
                    "dataset_id": "mmlu.dev.v1",
                    "sample_size": 8,
                    "scoring_mode": "normalized_exact_match",
                    "win_count": 5,
                    "loss_count": 1,
                    "tie_count": 2,
                    "regression_count": 1,
                    "base_accuracy": 0.5,
                    "target_accuracy": 1.0,
                    "delta_accuracy": 0.5,
                    "effect_threshold": 0.1,
                    "verdict": "improvement",
                    "category_breakdown": {
                        "math": {
                            "sample_size": 8,
                            "base_accuracy": 0.5,
                            "target_accuracy": 1.0,
                            "delta_accuracy": 0.5,
                        }
                    },
                    "statistical_evidence": {
                        "sample_size": 8,
                        "delta_accuracy": 0.5,
                        "bootstrap": {
                            "method": "paired_bootstrap_percentile",
                            "confidence_level": 0.95,
                            "lower_bound": 0.12,
                            "upper_bound": 0.84,
                            "crosses_zero": False,
                            "iterations": 400,
                            "seed": 9,
                        },
                        "analytical": {
                            "method": "paired_difference_normal_approximation",
                            "confidence_level": 0.95,
                            "lower_bound": 0.18,
                            "upper_bound": 0.82,
                            "crosses_zero": False,
                        },
                    },
                    "release_gate_summary": {
                        "verdict": "improvement",
                        "reason": "delta_exceeds_threshold_with_supported_intervals",
                        "effect_threshold": 0.1,
                        "delta_accuracy": 0.5,
                        "threshold_passed": True,
                        "both_intervals_same_side": True,
                    },
                    "duration_seconds": 3.25,
                    "metrics": [
                        {"name": "eval.compare.delta_typed_score_mean", "value": 0.5, "unit": "ratio"},
                        {"name": "eval.compare.base_accuracy", "value": 0.5, "unit": "ratio"},
                        {"name": "eval.compare.delta_accuracy", "value": 0.5, "unit": "ratio"},
                        {"name": "eval.compare.target_accuracy", "value": 1.0, "unit": "ratio"},
                        {"name": "eval.compare.win_count", "value": 5.0, "unit": "count"},
                    ],
                    "report_path": str(root / "evaluation-compare-report.md"),
                },
            ],
        }) + "\n"
    )
    (root / "evaluation-compare-samples.jsonl").write_text(
        "\n".join([
            json.dumps({
                "schema_version": "melix.evaluation_compare_sample.v2",
                "job_id": "eval-compare-1",
                "suite_id": "mmlu",
                "dataset_id": "mmlu.dev.v1",
                "sample_id": "sample-1",
                "target_model_id": "melix-dev-text-lora-a",
                "input_text": "2+2?",
                "target": "4",
                "base_extracted_result": "3",
                "target_extracted_result": "4",
                "base_raw_response": "3",
                "target_raw_response": "4",
                "base_typed_score": 0.0,
                "target_typed_score": 1.0,
                "outcome": "win",
                "regression_kind": "",
                "base_time_s": 0.03,
                "target_time_s": 0.02,
                "base_extraction_status": "extracted",
                "target_extraction_status": "extracted",
                "base_validation_status": "validated",
                "target_validation_status": "validated",
                "base_failure_reason": "",
                "target_failure_reason": "",
                "base_parse_status": "parsed",
                "target_parse_status": "parsed",
                "category_label": "math",
                "subject_label": "algebra",
            }),
        ]) + "\n"
    )


def test_collect_benchmark_artifacts_finds_persisted_bench_files(tmp_path: Path) -> None:
    _write_bench_fixtures(tmp_path)

    result = collect_benchmark_artifacts(tmp_path)

    assert len(result["benchmark_jobs"]) == 1
    assert result["benchmark_jobs"][0]["job_id"] == "bench-1"
    assert result["benchmark_jobs"][0]["task_kind"] == "text-generation"
    assert len(result["benchmark_summary_rows"]) == 1
    assert len(result["benchmark_context_rows"]) == 1
    assert len(result["benchmark_batch_rows"]) == 1
    assert len(result["benchmark_results"]) == 1
    assert result["benchmark_results"][0]["suite"] == "smoke"


def test_collect_benchmark_artifacts_falls_back_to_legacy_job_json(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    root.mkdir(parents=True, exist_ok=True)
    (root / "bench-job.json").write_text(
        json.dumps({
            "schema_version": "melix.serving_benchmark_job.v1",
            "job_id": "bench-legacy",
            "model_id": "melix-dev-text",
            "suites": ["smoke"],
            "parameters": {},
            "status": "completed",
        }) + "\n"
    )

    result = collect_benchmark_artifacts(root)

    assert len(result["benchmark_jobs"]) == 1
    assert result["benchmark_jobs"][0]["job_id"] == "bench-legacy"


def test_collect_benchmark_artifacts_reads_per_run_history_from_runs_directory(
    tmp_path: Path,
) -> None:
    bench_root = tmp_path / "bench"
    _write_bench_run_fixture(bench_root, job_id="bench-1", model_id="model-a", ttft_ms=11.0)
    _write_bench_run_fixture(bench_root, job_id="bench-2", model_id="model-b", ttft_ms=13.5)

    result = collect_benchmark_artifacts(tmp_path)

    assert [job["job_id"] for job in result["benchmark_jobs"]] == ["bench-1", "bench-2"]
    assert [row["job_id"] for row in result["benchmark_results"]] == ["bench-1", "bench-2"]
    assert [row["job_id"] for row in result["benchmark_context_rows"]] == ["bench-1", "bench-2"]
    assert [row["job_id"] for row in result["benchmark_batch_rows"]] == ["bench-1", "bench-2"]


def test_collect_benchmark_run_uses_single_directory_scan_without_path_is_file_probes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "bench-run"
    _write_bench_fixtures(run_root)
    (run_root / "bench-job.json").write_text(json.dumps({"job_id": "legacy-bench"}) + "\n")
    (run_root / "bench-result-z.json").write_text(json.dumps({"job_id": "bench-1", "suite": "zeta"}) + "\n")
    (run_root / "bench-result-a.json").write_text(json.dumps({"job_id": "bench-1", "suite": "alpha"}) + "\n")

    scandir_calls = 0
    original_scandir = __import__("os").scandir
    original_is_file = Path.is_file

    def tracked_scandir(path: str | bytes | int | Path):
        nonlocal scandir_calls
        if Path(path) == run_root:
            scandir_calls += 1
        return original_scandir(path)

    def fail_run_file_probes(path: Path) -> bool:
        if path.parent == run_root:
            raise AssertionError(f"unexpected Path.is_file probe for {path.name}")
        return original_is_file(path)

    with pytest.raises(AssertionError, match="bench-summary.json"):
        fail_run_file_probes(run_root / "bench-summary.json")
    assert fail_run_file_probes(tmp_path / "outside.json") is False

    monkeypatch.setattr("worker.productization.benchmark_export.os.scandir", tracked_scandir)
    monkeypatch.setattr(Path, "is_file", fail_run_file_probes)

    summary_rows: list[dict[str, object]] = []
    context_rows: list[dict[str, object]] = []
    batch_rows: list[dict[str, object]] = []
    results: list[dict[str, object]] = []

    _collect_benchmark_run(
        run_root,
        summary_rows=summary_rows,
        context_rows=context_rows,
        batch_rows=batch_rows,
        results=results,
    )

    assert scandir_calls == 1
    assert [row["job_id"] for row in summary_rows] == ["bench-1"]
    assert [row["job_id"] for row in context_rows] == ["bench-1"]
    assert [row["job_id"] for row in batch_rows] == ["bench-1"]
    assert [row["suite"] for row in results] == ["alpha", "smoke", "zeta"]


def test_collect_benchmark_run_prefers_summary_over_legacy_job_and_preserves_result_order(tmp_path: Path) -> None:
    run_root = tmp_path / "bench-run"
    _write_bench_fixtures(run_root)
    (run_root / "bench-job.json").write_text(
        json.dumps({"job_id": "bench-legacy", "model_id": "legacy-model", "status": "completed"}) + "\n"
    )
    (run_root / "bench-result-z.json").write_text(json.dumps({"job_id": "bench-1", "suite": "zeta"}) + "\n")
    (run_root / "bench-result-a.json").write_text(json.dumps({"job_id": "bench-1", "suite": "alpha"}) + "\n")

    result = collect_benchmark_artifacts(run_root)

    assert [job["job_id"] for job in result["benchmark_jobs"]] == ["bench-1"]
    assert result["benchmark_jobs"][0]["model_id"] == "melix-dev-text"
    assert [row["suite"] for row in result["benchmark_results"]] == ["alpha", "smoke", "zeta"]


def test_collect_benchmark_run_skips_unreadable_entries_during_single_scan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "bench-run"
    _write_bench_fixtures(run_root)

    class _BrokenEntry:
        name = "bench-result-broken.json"

        def is_file(self) -> bool:
            raise OSError("stat failed")

    class _SummaryEntry:
        name = "bench-summary.json"

        def is_file(self) -> bool:
            return True

    class _ContextEntry:
        name = "bench-context-rows.jsonl"

        def is_file(self) -> bool:
            return True

    class _BatchEntry:
        name = "bench-batch-rows.jsonl"

        def is_file(self) -> bool:
            return True

    class _ResultEntry:
        name = "bench-result-smoke.json"

        def is_file(self) -> bool:
            return True

    class _Scandir:
        def __enter__(self):
            return iter((_BrokenEntry(), _SummaryEntry(), _ContextEntry(), _BatchEntry(), _ResultEntry()))

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setattr("worker.productization.benchmark_export.os.scandir", lambda path: _Scandir())

    summary_rows: list[dict[str, object]] = []
    context_rows: list[dict[str, object]] = []
    batch_rows: list[dict[str, object]] = []
    results: list[dict[str, object]] = []

    _collect_benchmark_run(
        run_root,
        summary_rows=summary_rows,
        context_rows=context_rows,
        batch_rows=batch_rows,
        results=results,
    )

    assert [row["job_id"] for row in summary_rows] == ["bench-1"]
    assert [row["job_id"] for row in context_rows] == ["bench-1"]
    assert [row["job_id"] for row in batch_rows] == ["bench-1"]
    assert [row["suite"] for row in results] == ["smoke"]


def test_collect_benchmark_run_skips_missing_or_unreadable_payloads_after_single_scan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "bench-run"
    _write_bench_fixtures(run_root)
    (run_root / "bench-job.json").write_text(json.dumps({"job_id": "legacy-bench", "status": "completed"}) + "\n")
    (run_root / "bench-result-a.json").write_text(json.dumps({"job_id": "bench-1", "suite": "alpha"}) + "\n")

    original_load_json_object = _load_json_object
    original_iter_jsonl_dict_rows = _iter_jsonl_dict_rows

    def flaky_load_json_object(path: Path) -> dict[str, object]:
        if path.name == "bench-summary.json":
            raise FileNotFoundError(path)
        if path.name == "bench-result-smoke.json":
            raise OSError("result vanished")
        return original_load_json_object(path)

    def flaky_iter_jsonl_dict_rows(path: Path):
        if path.name == "bench-context-rows.jsonl":
            raise OSError("context vanished")
        yield from original_iter_jsonl_dict_rows(path)

    monkeypatch.setattr("worker.productization.benchmark_export._load_json_object", flaky_load_json_object)
    monkeypatch.setattr("worker.productization.benchmark_export._iter_jsonl_dict_rows", flaky_iter_jsonl_dict_rows)

    summary_rows: list[dict[str, object]] = []
    context_rows: list[dict[str, object]] = []
    batch_rows: list[dict[str, object]] = []
    results: list[dict[str, object]] = []

    _collect_benchmark_run(
        run_root,
        summary_rows=summary_rows,
        context_rows=context_rows,
        batch_rows=batch_rows,
        results=results,
    )

    assert [row["job_id"] for row in summary_rows] == ["legacy-bench"]
    assert context_rows == []
    assert [row["job_id"] for row in batch_rows] == ["bench-1"]
    assert [row["suite"] for row in results] == ["alpha"]


def test_collect_benchmark_artifacts_reads_matrix_run_history_from_matrix_runs_directory(
    tmp_path: Path,
) -> None:
    bench_root = tmp_path / "bench"
    _write_bench_matrix_run_fixture(bench_root, job_id="bench-matrix-1")
    _write_bench_matrix_run_fixture(bench_root, job_id="bench-matrix-2")

    result = collect_benchmark_artifacts(tmp_path)

    assert [job["job_id"] for job in result["benchmark_matrix_jobs"]] == ["bench-matrix-1", "bench-matrix-2"]
    assert [row["job_id"] for row in result["benchmark_matrix_summary_rows"]] == ["bench-matrix-1", "bench-matrix-2"]
    assert [row["job_id"] for row in result["benchmark_matrix_request_rows"]] == ["bench-matrix-1", "bench-matrix-2"]


def test_iter_sorted_child_directories_returns_sorted_directories(tmp_path: Path) -> None:
    parent = tmp_path / "artifacts"
    (parent / "b_dir").mkdir(parents=True)
    (parent / "a_dir").mkdir(parents=True)
    (parent / "c_file").write_text("x")
    (parent / "a_file.txt").write_text("x")

    # ensure non-directories are ignored and ordering is lexical
    assert [path.name for path in _iter_sorted_child_directories(parent)] == ["a_dir", "b_dir"]


def test_iter_sorted_child_directories_nonexistent_root_returns_empty() -> None:
    assert _iter_sorted_child_directories(Path("/tmp/this-path-should-not-exist-12345")) == ()


def test_iter_sorted_matching_files_returns_lexically_sorted_matching_files(tmp_path: Path) -> None:
    parent = tmp_path / "artifacts"
    parent.mkdir(parents=True)
    (parent / "bench-result-b.json").write_text("{}\n")
    (parent / "bench-result-a.json").write_text("{}\n")
    (parent / "bench-result-z.json").mkdir()
    (parent / "other.json").write_text("{}\n")

    assert [path.name for path in _iter_sorted_matching_files(parent, prefix="bench-result-", suffix=".json")] == [
        "bench-result-a.json",
        "bench-result-b.json",
    ]


def test_load_json_object_reads_json_without_read_text_round_trip(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps({"job_id": "bench-1", "status": "completed"}) + "\n")

    assert _load_json_object(payload_path) == {"job_id": "bench-1", "status": "completed"}


def test_load_json_object_rejects_non_object_payload(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(["not", "an", "object"]) + "\n")

    with pytest.raises(TypeError, match="expected JSON object"):
        _load_json_object(payload_path)


def test_iter_sorted_matching_files_skips_entries_with_stat_failures(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    parent = tmp_path / "artifacts"
    parent.mkdir(parents=True)

    class _BrokenEntry:
        name = "bench-result-broken.json"

        def is_file(self) -> bool:
            raise OSError("stat failed")

    class _GoodEntry:
        name = "bench-result-ok.json"

        def is_file(self) -> bool:
            return True

    class _Scandir:
        def __enter__(self):
            return iter((_BrokenEntry(), _GoodEntry()))

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setattr("worker.productization.benchmark_export.os.scandir", lambda path: _Scandir())

    assert [path.name for path in _iter_sorted_matching_files(parent, prefix="bench-result-", suffix=".json")] == [
        "bench-result-ok.json",
    ]


def test_collect_benchmark_artifacts_ignores_blank_and_non_object_jsonl_rows(tmp_path: Path) -> None:
    _write_bench_fixtures(tmp_path)
    (tmp_path / "bench-context-rows.jsonl").write_text(
        "\n".join([
            "",
            json.dumps({"job_id": "bench-1", "row_kind": "context"}),
            json.dumps(["ignored"]),
            "   ",
        ]) + "\n"
    )
    (tmp_path / "bench-batch-rows.jsonl").write_text(
        "\n".join([
            json.dumps({"job_id": "bench-1", "row_kind": "batch"}),
            json.dumps("ignored"),
        ]) + "\n"
    )
    matrix_root = tmp_path / "matrix-runs" / "bench-matrix-1"
    matrix_root.mkdir(parents=True, exist_ok=True)
    (matrix_root / "bench-matrix-job.json").write_text(json.dumps({"job_id": "bench-matrix-1"}) + "\n")
    (matrix_root / "bench-matrix-summary.jsonl").write_text(
        "\n".join([
            json.dumps({"job_id": "bench-matrix-1", "row_kind": "summary"}),
            json.dumps(123),
        ]) + "\n"
    )
    (matrix_root / "bench-matrix-requests.jsonl").write_text(
        "\n".join([
            "",
            json.dumps({"job_id": "bench-matrix-1", "row_kind": "request"}),
            json.dumps(False),
        ]) + "\n"
    )

    result = collect_benchmark_artifacts(tmp_path)

    assert result["benchmark_context_rows"] == [{"job_id": "bench-1", "row_kind": "context"}]
    assert result["benchmark_batch_rows"] == [{"job_id": "bench-1", "row_kind": "batch"}]
    assert result["benchmark_matrix_summary_rows"] == [{"job_id": "bench-matrix-1", "row_kind": "summary"}]
    assert result["benchmark_matrix_request_rows"] == [{"job_id": "bench-matrix-1", "row_kind": "request"}]


def test_iter_jsonl_dict_rows_streams_rows_lazily(tmp_path: Path) -> None:
    path = tmp_path / "streamed.jsonl"
    path.write_text(
        "\n".join([
            json.dumps({"job_id": "bench-1", "row_kind": "context"}),
            "not-json",
        ]) + "\n",
        encoding="utf-8",
    )

    rows = _iter_jsonl_dict_rows(path)

    assert next(rows) == {"job_id": "bench-1", "row_kind": "context"}
    with pytest.raises(json.JSONDecodeError):
        next(rows)


def test_collect_evaluation_run_uses_single_directory_scan_without_path_is_file_probes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "eval-run"
    _write_eval_fixtures(run_root)
    _write_eval_compare_fixtures(run_root)

    scandir_calls = 0
    original_scandir = __import__("os").scandir
    original_is_file = Path.is_file

    def tracked_scandir(path: str | bytes | int | Path):
        nonlocal scandir_calls
        if Path(path) == run_root:
            scandir_calls += 1
        return original_scandir(path)

    def fail_run_file_probes(path: Path) -> bool:
        if path.parent == run_root:
            raise AssertionError(f"unexpected Path.is_file probe for {path.name}")
        return original_is_file(path)

    with pytest.raises(AssertionError, match="evaluation-job.json"):
        fail_run_file_probes(run_root / "evaluation-job.json")
    assert fail_run_file_probes(tmp_path / "outside.json") is False

    monkeypatch.setattr("worker.productization.benchmark_export.os.scandir", tracked_scandir)
    monkeypatch.setattr(Path, "is_file", fail_run_file_probes)

    jobs: list[dict[str, object]] = []
    results: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    samples: list[dict[str, object]] = []
    compare_jobs: list[dict[str, object]] = []
    compare_summary_rows: list[dict[str, object]] = []
    compare_samples: list[dict[str, object]] = []

    _collect_evaluation_run(
        run_root,
        jobs=jobs,
        results=results,
        summaries=summaries,
        samples=samples,
        compare_jobs=compare_jobs,
        compare_summary_rows=compare_summary_rows,
        compare_samples=compare_samples,
    )

    assert scandir_calls == 1
    assert [job["job_id"] for job in jobs] == ["eval-1", "eval-compare-1"]
    assert [row["job_id"] for row in results] == ["eval-1", "eval-compare-1"]
    assert [row["job_id"] for row in summaries] == ["eval-1", "eval-compare-1"]
    assert [sample["sample_id"] for sample in compare_samples] == ["sample-1"]
    assert [sample["sample_id"] for sample in samples] == ["1", "melix-dev-text-lora-a:sample-1"]


def test_collect_evaluation_run_preserves_load_failure_behavior_after_discovery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "eval-run"
    _write_eval_fixtures(run_root)

    original_load_json_object = __import__(
        "worker.productization.benchmark_export",
        fromlist=["_load_json_object"],
    )._load_json_object

    def flaky_load_json_object(path: Path) -> dict[str, object]:
        if path == run_root / "evaluation-job.json":
            raise FileNotFoundError(path)
        return original_load_json_object(path)

    monkeypatch.setattr("worker.productization.benchmark_export._load_json_object", flaky_load_json_object)

    with pytest.raises(FileNotFoundError):
        _collect_evaluation_run(
            run_root,
            jobs=[],
            results=[],
            summaries=[],
            samples=[],
            compare_jobs=[],
            compare_summary_rows=[],
            compare_samples=[],
        )


def test_collect_evaluation_artifacts_ignores_blank_and_non_object_jsonl_rows(tmp_path: Path) -> None:
    _write_eval_compare_fixtures(tmp_path)
    (tmp_path / "evaluation-samples.jsonl").write_text(
        "\n".join([
            "",
            json.dumps({"job_id": "eval-1", "sample_id": "kept"}),
            json.dumps(["ignored"]),
        ]) + "\n"
    )
    (tmp_path / "evaluation-compare-samples.jsonl").write_text(
        "\n".join([
            json.dumps({
                "sample_id": "sample-1",
                "target_model_id": "melix-dev-text-lora-a",
                "base_model_id": "melix-dev-text",
                "suite_id": "mmlu",
                "dataset_id": "mmlu.dev.v1",
                "input_text": "2+2?",
                "target": "4",
                "base_extracted_result": "4",
                "target_extracted_result": "4",
                "base_raw_response": "4",
                "target_raw_response": "4",
                "base_typed_score": 1.0,
                "target_typed_score": 1.0,
                "outcome": "tie",
            }),
            json.dumps("ignored"),
        ]) + "\n"
    )

    result = collect_evaluation_artifacts(tmp_path)

    assert [sample["sample_id"] for sample in result["evaluation_compare_samples"]] == ["sample-1"]
    assert [sample["sample_id"] for sample in result["evaluation_samples"]] == ["kept", "melix-dev-text-lora-a:sample-1"]


def test_collect_evaluation_artifacts_finds_persisted_eval_files(tmp_path: Path) -> None:
    _write_eval_fixtures(tmp_path)

    result = collect_evaluation_artifacts(tmp_path)

    assert len(result["evaluation_jobs"]) == 1
    assert result["evaluation_jobs"][0]["job_id"] == "eval-1"
    assert len(result["evaluation_results"]) == 1
    assert result["evaluation_results"][0]["suite_id"] == "mmlu"
    assert len(result["evaluation_samples"]) == 1
    assert result["evaluation_samples"][0]["sample_id"] == "1"


def test_collect_evaluation_artifacts_prefers_persisted_summary_json_when_present(tmp_path: Path) -> None:
    _write_eval_fixtures(tmp_path)
    (tmp_path / "evaluation-summary.json").write_text(
        json.dumps({
            "job_id": "eval-1",
            "model_id": "summary-model",
            "primary_score_name": "typed_score_mean",
            "primary_score_value": 0.99,
        }) + "\n"
    )

    result = collect_evaluation_artifacts(tmp_path)

    assert result["evaluation_summary_rows"] == [
        {
            "job_id": "eval-1",
            "model_id": "summary-model",
            "primary_score_name": "typed_score_mean",
            "primary_score_value": 0.99,
        }
    ]


def test_collect_evaluation_artifacts_reads_per_run_history_from_runs_directory(
    tmp_path: Path,
) -> None:
    evaluation_root = tmp_path / "evaluation"
    _write_eval_fixtures(evaluation_root / "runs" / "eval-1")
    _write_eval_fixtures(evaluation_root / "runs" / "eval-2")

    result = collect_evaluation_artifacts(tmp_path)

    assert [job["job_id"] for job in result["evaluation_jobs"]] == ["eval-1", "eval-1"]
    assert [row["job_id"] for row in result["evaluation_results"]] == ["eval-1", "eval-1"]
    assert [sample["job_id"] for sample in result["evaluation_samples"]] == ["eval-1", "eval-1"]


def test_collect_evaluation_artifacts_normalizes_compare_runs_for_history_and_exports(
    tmp_path: Path,
) -> None:
    evaluation_root = tmp_path / "evaluation"
    _write_eval_compare_fixtures(evaluation_root / "runs" / "eval-compare-1")

    result = collect_evaluation_artifacts(tmp_path)

    assert [job["job_id"] for job in result["evaluation_jobs"]] == ["eval-compare-1"]
    assert result["evaluation_jobs"][0]["model_id"] == "melix-dev-text"
    assert result["evaluation_jobs"][0]["parameters"]["compare_target_model_ids"] == "melix-dev-text-lora-a"
    assert [row["job_id"] for row in result["evaluation_results"]] == ["eval-compare-1"]
    assert result["evaluation_results"][0]["report_path"].endswith("evaluation-compare-report.md")
    assert result["evaluation_summary_rows"][0]["model_id"] == "melix-dev-text-lora-a"
    assert result["evaluation_summary_rows"][0]["primary_score_name"] == "eval.compare.delta_typed_score_mean"
    assert result["evaluation_summary_rows"][0]["primary_score_value"] == 0.5
    assert result["evaluation_summary_rows"][0]["effect_threshold"] == 0.1
    assert result["evaluation_summary_rows"][0]["verdict"] == "improvement"
    assert result["evaluation_summary_rows"][0]["bootstrap_lower_bound"] == 0.12
    assert result["evaluation_summary_rows"][0]["analytical_upper_bound"] == 0.82
    assert result["evaluation_samples"][0]["job_id"] == "eval-compare-1"
    assert result["evaluation_samples"][0]["sample_id"] == "melix-dev-text-lora-a:sample-1"
    assert result["evaluation_samples"][0]["task_kind"] == "text-generation"
    assert result["evaluation_samples"][0]["extracted_result"] == "4"
    assert result["evaluation_samples"][0]["code_language"] == ""
    assert result["evaluation_samples"][0]["extraction_status"] == "extracted"
    assert result["evaluation_samples"][0]["validation_status"] == "validated"
    assert result["evaluation_samples"][0]["category_label"] == "math"
    assert result["evaluation_samples"][0]["subject_label"] == "algebra"
    assert result["evaluation_compare_jobs"][0]["job_id"] == "eval-compare-1"
    assert result["evaluation_compare_summary_rows"][0]["target_model_id"] == "melix-dev-text-lora-a"
    assert result["evaluation_compare_samples"][0]["job_id"] == "eval-compare-1"
    assert result["evaluation_compare_samples"][0]["sample_id"] == "sample-1"
    assert result["evaluation_compare_samples"][0]["target_extracted_result"] == "4"
    assert result["evaluation_compare_samples"][0]["base_extraction_status"] == "extracted"
    assert result["evaluation_compare_samples"][0]["category_label"] == "math"


def test_build_export_bundle_combines_benchmark_and_evaluation_artifacts(tmp_path: Path) -> None:
    _write_bench_fixtures(tmp_path)
    _write_bench_matrix_run_fixture(tmp_path / "bench", job_id="bench-matrix-1")
    _write_eval_fixtures(tmp_path)

    bundle = build_export_bundle(tmp_path)

    assert bundle["export_schema_version"] == "melix.benchmark_export.v1"
    assert isinstance(bundle["exported_at_unix_ms"], int)
    assert len(bundle["benchmark_jobs"]) == 1
    assert len(bundle["benchmark_summary_rows"]) == 1
    assert len(bundle["benchmark_context_rows"]) == 1
    assert len(bundle["benchmark_batch_rows"]) == 1
    assert len(bundle["benchmark_matrix_jobs"]) == 1
    assert len(bundle["benchmark_matrix_summary_rows"]) == 1
    assert len(bundle["benchmark_matrix_request_rows"]) == 1
    assert len(bundle["evaluation_jobs"]) == 1
    assert len(bundle["evaluation_samples"]) == 1


def test_build_export_bundle_collects_benchmark_and_evaluation_from_model_ops_root(
    tmp_path: Path,
) -> None:
    jobs_root = tmp_path / "model-ops"
    _write_bench_fixtures(jobs_root / "bench")
    _write_bench_matrix_run_fixture(jobs_root / "bench", job_id="bench-matrix-1")
    _write_eval_fixtures(jobs_root / "evaluation")

    bundle = build_export_bundle(jobs_root)

    assert len(bundle["benchmark_jobs"]) == 1
    assert len(bundle["benchmark_results"]) == 1
    assert len(bundle["benchmark_summary_rows"]) == 1
    assert len(bundle["benchmark_matrix_jobs"]) == 1
    assert len(bundle["benchmark_matrix_summary_rows"]) == 1
    assert len(bundle["benchmark_matrix_request_rows"]) == 1
    assert len(bundle["evaluation_jobs"]) == 1
    assert len(bundle["evaluation_results"]) == 1
    assert len(bundle["evaluation_samples"]) == 1


def test_write_export_bundle_persists_structured_json(tmp_path: Path) -> None:
    _write_bench_fixtures(tmp_path)
    output = tmp_path / "export" / "bundle.json"

    result_path = write_export_bundle(tmp_path, output)

    assert result_path == output
    assert output.exists()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["export_schema_version"] == "melix.benchmark_export.v1"
    assert len(payload["benchmark_jobs"]) == 1


def test_build_benchmark_summary_csv_uses_canonical_rows(tmp_path: Path) -> None:
    _write_bench_fixtures(tmp_path)
    bundle = build_export_bundle(tmp_path)

    csv_text = build_benchmark_summary_csv(bundle)

    assert "job_id,model_id,task_kind,source_repo" in csv_text.splitlines()[0]
    assert "bench-1,melix-dev-text,text-generation,HuggingFaceH4/ultrachat_200k" in csv_text


def test_build_benchmark_summary_csv_serializes_tuple_and_none_values() -> None:
    bundle = {
        "benchmark_summary_rows": [
            {
                "job_id": "bench-9",
                "model_id": "melix-dev-text",
                "task_kind": "text-generation",
                "source_repo": "HuggingFaceH4/ultrachat_200k",
                "suites": ("smoke", "latency"),
                "context_lengths": (16, 32),
                "generation_length": 8,
                "batch_sizes": (1, 2),
                "repeats": 2,
                "cache_profile": "cold",
                "reasoning_mode": None,
                "structured_output_mode": None,
                "request_p50_ms": 11.0,
                "request_p95_ms": 12.0,
                "status": "completed",
                "output_dir": "/tmp",
                "created_at_unix_ms": 1,
                "updated_at_unix_ms": 2,
            }
        ]
    }

    csv_text = build_benchmark_summary_csv(bundle)

    assert "smoke,latency" in csv_text
    assert "16,32" in csv_text


def test_build_benchmark_context_and_batch_csv_use_canonical_rows(tmp_path: Path) -> None:
    _write_bench_fixtures(tmp_path)
    bundle = build_export_bundle(tmp_path)

    context_csv = build_benchmark_context_csv(bundle)
    batch_csv = build_benchmark_batch_csv(bundle)

    assert "context_length,generation_length,batch_size,repeat_index" in context_csv.splitlines()[0]
    assert "context_length,generation_length,batch_size,repeat_index" in batch_csv.splitlines()[0]
    assert "bench-1,melix-dev-text,text-generation,HuggingFaceH4/ultrachat_200k,smoke,32,8,1,0" in context_csv
    assert "bench-1,melix-dev-text,text-generation,HuggingFaceH4/ultrachat_200k,smoke,32,8,1,0" in batch_csv


def test_build_benchmark_matrix_summary_and_requests_csv_use_canonical_rows(tmp_path: Path) -> None:
    _write_bench_matrix_run_fixture(tmp_path / "bench", job_id="bench-matrix-1")
    bundle = build_export_bundle(tmp_path)

    summary_csv = build_benchmark_matrix_summary_csv(bundle)
    requests_csv = build_benchmark_matrix_requests_csv(bundle)

    summary_lines = summary_csv.splitlines()
    request_lines = requests_csv.splitlines()
    assert "job_id,task_kind,source_repo,model_id,suite_id,context_length" in summary_lines[0]
    assert "cell_wall_ms,completed_count,failed_count" in summary_lines[0]
    assert "job_id,cell_id,task_kind,suite_id,context_length,generation_length" in request_lines[0]
    assert "dataset_materialize_ms,prompt_render_ms,warmup_ms" in request_lines[0]
    assert summary_lines[1].startswith(
        "bench-matrix-1,text-generation,HuggingFaceH4/ultrachat_200k,melix-dev-text,smoke,1024,128,2,cold,enabled,plain_text,1,3,24,0,24.45,1.2,88.4,3.1,1400.0,58.2,3.8,221.5,1.0,2147483648,5.1,9.2,"
    )
    assert summary_lines[1].endswith("111")
    assert request_lines[1].startswith(
        "bench-matrix-1,cell-1,text-generation,smoke,1024,128,2,cold,enabled,plain_text,1,0,0,24.45,88.4,1400.0,58.2,5.1,2147483648,completed,,"
    )
    assert request_lines[1].endswith("111")


def test_export_csv_preserves_probe_columns() -> None:
    bundle = {
        "benchmark_context_rows": [
            {
                "job_id": "bench-1",
                "model_id": "model-a",
                "task_kind": "text-generation",
                "source_repo": "repo/a",
                "suite": "smoke",
                "context_length": 32,
                "generation_length": 8,
                "batch_size": 1,
                "repeat_index": 0,
                "prefill_tokens_per_second": 24.45,
                "decode_tokens_per_second": 47.08,
                "ttft_ms": 24.45,
                "request_latency_ms": 64.0,
                "peak_memory_bytes": 2048.0,
                "speedup_vs_batch_1": 1.0,
                "cache_profile": "warm",
                "reasoning_mode": "",
                "structured_output_mode": "",
                "dataset_materialize_ms": 2.0,
                "prompt_render_ms": 1.0,
                "warmup_ms": 4.0,
                "prefill_ms": 24.45,
                "decode_ms": 39.55,
                "tokens_in": 32,
                "tokens_out": 8,
                "first_token_index": 1,
                "cache_hit": True,
                "runtime_kind": "text",
                "error_stage": "",
            }
        ],
        "benchmark_matrix_summary_rows": [
            {
                "job_id": "matrix-1",
                "task_kind": "text-generation",
                "source_repo": "repo/a",
                "model_id": "model-a",
                "suite_id": "smoke",
                "context_length": 32,
                "generation_length": 8,
                "batch_size": 1,
                "cache_profile": "warm",
                "reasoning_mode": "",
                "structured_output_mode": "",
                "concurrency_level": 1,
                "repeats": 1,
                "requests": 2,
                "duration_seconds": 0,
                "ttft_mean_ms": 24.45,
                "ttft_std_ms": 0.2,
                "request_latency_mean_ms": 64.0,
                "request_latency_std_ms": 0.4,
                "prefill_tokens_per_second_mean": 24.45,
                "decode_tokens_per_second_mean": 47.08,
                "throughput_requests_per_second": 2.0,
                "throughput_tokens_per_second": 94.16,
                "success_rate": 1.0,
                "peak_memory_bytes_max": 2048,
                "queue_wait_mean_ms": 0.0,
                "queue_wait_p95_ms": 0.0,
                "cell_wall_ms": 128.0,
                "completed_count": 2,
                "failed_count": 0,
                "ttft_p50_ms": 24.45,
                "ttft_p95_ms": 24.7,
                "request_latency_p50_ms": 64.0,
                "request_latency_p95_ms": 64.4,
                "created_at_unix_ms": 111,
            }
        ],
    }

    context_header = build_benchmark_context_csv(bundle).splitlines()[0]
    matrix_header = build_benchmark_matrix_summary_csv(bundle).splitlines()[0]

    assert "dataset_materialize_ms,prompt_render_ms,warmup_ms,prefill_ms,decode_ms" in context_header
    assert "tokens_in,tokens_out,first_token_index,cache_hit,runtime_kind,error_stage" in context_header
    assert "cell_wall_ms,completed_count,failed_count,ttft_p50_ms,ttft_p95_ms" in matrix_header


def test_build_comparison_table_produces_markdown_with_metric_columns() -> None:
    run_a = {
        "benchmark_jobs": [{"job_id": "bench-a", "model_id": "model-a"}],
        "benchmark_results": [{
            "suite": "smoke",
            "metrics": [
                {"name": "bench.smoke.ttft_ms", "value": 24.45},
                {"name": "bench.smoke.tokens_per_second", "value": 47.08},
            ],
        }],
    }
    run_b = {
        "benchmark_jobs": [{"job_id": "bench-b", "model_id": "model-b"}],
        "benchmark_results": [{
            "suite": "smoke",
            "metrics": [
                {"name": "bench.smoke.ttft_ms", "value": 22.10},
                {"name": "bench.smoke.tokens_per_second", "value": 51.30},
            ],
        }],
    }

    table = build_comparison_table([run_a, run_b])

    assert "| Metric | model-a | model-b |" in table
    assert "| bench.smoke.ttft_ms | 24.45 | 22.10 |" in table
    assert "| bench.smoke.tokens_per_second | 47.08 | 51.30 |" in table


def test_build_comparison_table_handles_single_run() -> None:
    run = {
        "benchmark_jobs": [{"job_id": "bench-1", "model_id": "melix-dev"}],
        "benchmark_results": [{
            "suite": "smoke",
            "metrics": [{"name": "bench.smoke.ttft_ms", "value": 24.45}],
        }],
    }

    table = build_comparison_table([run])

    assert "| Metric | melix-dev |" in table
    assert "| bench.smoke.ttft_ms | 24.45 |" in table


def test_build_comparison_table_indexes_metrics_once_per_result() -> None:
    metrics = _CountingMetricList([
        {"name": "bench.smoke.ttft_ms", "value": 24.45},
        {"name": "bench.smoke.tokens_per_second", "value": 47.08},
    ])
    run = {
        "benchmark_jobs": [{"job_id": "bench-1", "model_id": "melix-dev"}],
        "benchmark_results": [{"suite": "smoke", "metrics": metrics}],
    }

    table = build_comparison_table([run])

    assert "| bench.smoke.ttft_ms | 24.45 |" in table
    assert "| bench.smoke.tokens_per_second | 47.08 |" in table
    assert metrics.iteration_count == 1


def test_build_comparison_table_ignores_blank_and_duplicate_metric_names() -> None:
    run = {
        "benchmark_jobs": [{"job_id": "bench-1", "model_id": "melix-dev"}],
        "benchmark_results": [{
            "suite": "smoke",
            "metrics": [
                {"name": "", "value": 999.0},
                {"name": "bench.smoke.ttft_ms", "value": 24.45},
                {"name": "bench.smoke.ttft_ms", "value": 88.88},
            ],
        }],
    }

    table = build_comparison_table([run])

    assert "|  |" not in table
    assert "| bench.smoke.ttft_ms | 24.45 |" in table
    assert "88.88" not in table


def test_build_comparison_table_ignores_evaluation_metrics() -> None:
    run = {
        "benchmark_jobs": [{"job_id": "run-1", "model_id": "melix-dev"}],
        "benchmark_results": [],
        "evaluation_results": [{
            "suite_id": "mmlu",
            "metrics": [{"name": "eval.mmlu.accuracy", "value": 0.75}],
        }],
    }

    table = build_comparison_table([run])

    assert table == ""


def test_collect_benchmark_artifacts_returns_empty_lists_for_nonexistent_directory(
    tmp_path: Path,
) -> None:
    result = collect_benchmark_artifacts(tmp_path / "does-not-exist")

    assert result["benchmark_jobs"] == []
    assert result["benchmark_summary_rows"] == []
    assert result["benchmark_context_rows"] == []
    assert result["benchmark_batch_rows"] == []
    assert result["benchmark_results"] == []
    assert result["benchmark_matrix_jobs"] == []
    assert result["benchmark_matrix_summary_rows"] == []
    assert result["benchmark_matrix_request_rows"] == []


def test_collect_evaluation_artifacts_returns_empty_lists_for_nonexistent_directory(
    tmp_path: Path,
) -> None:
    result = collect_evaluation_artifacts(tmp_path / "does-not-exist")

    assert result["evaluation_jobs"] == []
    assert result["evaluation_results"] == []
    assert result["evaluation_summary_rows"] == []
    assert result["evaluation_samples"] == []


def test_build_comparison_table_returns_empty_string_for_no_runs() -> None:
    assert build_comparison_table([]) == ""


def test_build_comparison_table_returns_empty_string_when_runs_have_no_metrics() -> None:
    run = {
        "benchmark_jobs": [{"job_id": "bench-empty", "model_id": "model-x"}],
        "benchmark_results": [],
    }

    assert build_comparison_table([run]) == ""


def test_build_comparison_table_uses_job_id_as_label_when_model_id_absent() -> None:
    run = {
        "benchmark_jobs": [{"job_id": "bench-no-model"}],
        "benchmark_results": [{
            "metrics": [{"name": "bench.smoke.ttft_ms", "value": 10.0}],
        }],
    }

    table = build_comparison_table([run])

    assert "| Metric | bench-no-model |" in table


def test_build_comparison_table_uses_run_index_label_when_no_jobs() -> None:
    run = {
        "benchmark_jobs": [],
        "benchmark_results": [{
            "metrics": [{"name": "bench.smoke.ttft_ms", "value": 10.0}],
        }],
    }

    table = build_comparison_table([run])

    assert "| Metric | run-0 |" in table


def test_evaluation_csv_builders_return_header_only_for_empty_bundle() -> None:
    empty_bundle: dict[str, object] = {}

    summary_csv = build_evaluation_summary_csv(empty_bundle)
    samples_csv = build_evaluation_samples_csv(empty_bundle)
    compare_summary_csv = build_evaluation_compare_summary_csv(empty_bundle)
    compare_samples_csv = build_evaluation_compare_samples_csv(empty_bundle)

    summary_lines = [line for line in summary_csv.splitlines() if line.strip()]
    samples_lines = [line for line in samples_csv.splitlines() if line.strip()]
    compare_summary_lines = [line for line in compare_summary_csv.splitlines() if line.strip()]
    compare_samples_lines = [line for line in compare_samples_csv.splitlines() if line.strip()]
    assert len(summary_lines) == 1
    assert summary_lines[0].startswith(
        "job_id,model_id,task_kind,source_repo,suite_id,dataset_id,primary_score_name,primary_score_value,sample_size,extraction_success_count,validation_success_count,scored_sample_count,failure_count,effect_threshold,verdict,bootstrap_lower_bound,bootstrap_upper_bound,analytical_lower_bound,analytical_upper_bound,duration_seconds,created_at_unix_ms"
    )
    assert len(samples_lines) == 1
    assert samples_lines[0].startswith(
        "job_id,suite_id,id,task_kind,target,extracted_result,input_text,raw_response,typed_score,time_s,extraction_status,validation_status,failure_reason,input_modalities,media_references,code_language,code_entry_point,code_compile_status,code_runtime_status,code_timeout_status,code_test_status,code_tests_passed,code_tests_total,code_failure_detail,category_label,subject_label"
    )
    assert len(compare_summary_lines) == 1
    assert compare_summary_lines[0].startswith("job_id,base_model_id,target_model_id")
    assert len(compare_samples_lines) == 1
    assert compare_samples_lines[0].startswith(
        "job_id,suite_id,dataset_id,sample_id,target_model_id"
    )


def test_evaluation_samples_csv_builder_maps_sample_id_and_preserves_modalities() -> None:
    bundle: dict[str, object] = {
        "evaluation_samples": [
            {
                "job_id": "eval-1",
                "suite_id": "humaneval",
                "sample_id": "sample-1",
                "task_kind": "text-generation",
                "correct": True,
                "expected": "identity",
                "predicted": "def identity(x):\n    return x",
                "question": "Write identity(x) that returns x.",
                "raw_response": "```python\ndef identity(x):\n    return x\n```",
                "time_s": 0.02,
                "parse_status": "parsed_code_block",
                "input_modalities": ["text"],
                "media_references": [],
                "code_language": "python",
                "code_entry_point": "identity",
                "code_compile_status": "compiled",
                "code_runtime_status": "ok",
                "code_timeout_status": "ok",
                "code_test_status": "passed",
                "code_tests_passed": 2,
                "code_tests_total": 2,
                "code_failure_detail": "",
            }
        ]
    }

    samples_csv = build_evaluation_samples_csv(bundle)
    rows = list(csv.DictReader(io.StringIO(samples_csv)))

    assert rows[0]["job_id"] == "eval-1"
    assert rows[0]["suite_id"] == "humaneval"
    assert rows[0]["id"] == "sample-1"
    assert rows[0]["task_kind"] == "text-generation"
    assert rows[0]["target"] == "identity"
    assert rows[0]["extracted_result"] == "def identity(x):\n    return x"
    assert rows[0]["input_text"] == "Write identity(x) that returns x."
    assert rows[0]["typed_score"] == "1.0"
    assert rows[0]["extraction_status"] == "extracted"
    assert rows[0]["validation_status"] == "validated"
    assert rows[0]["input_modalities"] == "text"


def test_rows_to_csv_accepts_generators_without_materializing_lists() -> None:
    rows = (
        {"job_id": f"eval-{index}", "typed_score": index / 10}
        for index in range(3)
    )

    csv_text = _rows_to_csv(rows, ["job_id", "typed_score"])

    assert list(csv.DictReader(io.StringIO(csv_text))) == [
        {"job_id": "eval-0", "typed_score": "0.0"},
        {"job_id": "eval-1", "typed_score": "0.1"},
        {"job_id": "eval-2", "typed_score": "0.2"},
    ]


def test_evaluation_compare_csv_builders_emit_compare_rows() -> None:
    bundle: dict[str, object] = {
        "evaluation_compare_summary_rows": [
            {
                "job_id": "eval-compare-1",
                "base_model_id": "melix-dev-text",
                "target_model_id": "melix-dev-text-lora-a",
                "suite_id": "mbpp",
                "dataset_id": "mbpp.dev.v1",
                "sample_size": 2,
                "win_count": 1,
                "loss_count": 0,
                "tie_count": 1,
                "regression_count": 0,
                "base_accuracy": 0.5,
                "target_accuracy": 1.0,
                "delta_accuracy": 0.5,
                "duration_seconds": 1.75,
            }
        ],
        "evaluation_compare_samples": [
            {
                "job_id": "eval-compare-1",
                "suite_id": "mbpp",
                "dataset_id": "mbpp.dev.v1",
                "sample_id": "sample-1",
                "target_model_id": "melix-dev-text-lora-a",
                "question": "Write solve(n) that returns n",
                "expected": "solve",
                "base_predicted": "def solve(n):\n    return 0",
                "target_predicted": "def solve(n):\n    return n",
                "base_raw_response": "def solve(n):\n    return 0",
                "target_raw_response": "def solve(n):\n    return n",
                "base_correct": False,
                "target_correct": True,
                "outcome": "win",
                "regression": False,
                "base_time_s": 0.11,
                "target_time_s": 0.09,
                "base_parse_status": "parsed_code_fallback",
                "target_parse_status": "parsed_code_fallback",
                "code_language": "python",
                "code_entry_point": "solve",
                "base_code_compile_status": "compiled",
                "target_code_compile_status": "compiled",
                "base_code_runtime_status": "ok",
                "target_code_runtime_status": "ok",
                "base_code_timeout_status": "ok",
                "target_code_timeout_status": "ok",
                "base_code_test_status": "failed",
                "target_code_test_status": "passed",
                "base_code_tests_passed": 1,
                "target_code_tests_passed": 2,
                "base_code_tests_total": 2,
                "target_code_tests_total": 2,
                "base_code_failure_detail": "assertion failed",
                "target_code_failure_detail": "",
                "category_label": "math",
                "subject_label": "algebra",
            }
        ],
    }

    summary_csv = build_evaluation_compare_summary_csv(bundle)
    samples_csv = build_evaluation_compare_samples_csv(bundle)

    assert "job_id,base_model_id,target_model_id" in summary_csv
    assert "eval-compare-1,melix-dev-text,melix-dev-text-lora-a,mbpp,mbpp.dev.v1,2,1,0,1,0,0.5,1.0,0.5,1.75" in summary_csv
    assert "job_id,suite_id,dataset_id,sample_id,target_model_id" in samples_csv
    assert "assertion failed" in samples_csv
    assert "math,algebra" in samples_csv


def test_benchmark_csv_builders_return_header_only_for_empty_bundle() -> None:
    empty_bundle: dict[str, object] = {}

    summary_csv = build_benchmark_summary_csv(empty_bundle)
    context_csv = build_benchmark_context_csv(empty_bundle)
    batch_csv = build_benchmark_batch_csv(empty_bundle)
    matrix_summary_csv = build_benchmark_matrix_summary_csv(empty_bundle)
    matrix_requests_csv = build_benchmark_matrix_requests_csv(empty_bundle)

    for csv_text, expected_prefix in [
        (summary_csv, "job_id,model_id,task_kind"),
        (context_csv, "job_id,model_id,task_kind"),
        (batch_csv, "job_id,model_id,task_kind"),
        (matrix_summary_csv, "job_id,task_kind,source_repo,model_id"),
        (matrix_requests_csv, "job_id,cell_id,task_kind"),
    ]:
        nonempty_lines = [line for line in csv_text.splitlines() if line.strip()]
        assert len(nonempty_lines) == 1, f"expected header-only CSV but got {nonempty_lines}"
        assert nonempty_lines[0].startswith(expected_prefix)
