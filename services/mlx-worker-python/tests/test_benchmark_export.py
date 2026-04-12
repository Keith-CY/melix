from __future__ import annotations

import json
from pathlib import Path

from worker.productization.benchmark_export import (
    build_comparison_table,
    build_benchmark_batch_csv,
    build_benchmark_context_csv,
    build_benchmark_matrix_requests_csv,
    build_benchmark_matrix_summary_csv,
    build_benchmark_summary_csv,
    build_evaluation_samples_csv,
    build_evaluation_summary_csv,
    build_export_bundle,
    collect_benchmark_artifacts,
    collect_evaluation_artifacts,
    write_export_bundle,
)


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
            "schema_version": "melix.evaluation_result.v1",
            "job_id": "eval-1",
            "suite_id": "mmlu",
            "metrics": [
                {"name": "eval.mmlu.accuracy", "value": 0.75, "unit": "ratio"},
            ],
        }) + "\n"
    )
    (root / "evaluation-samples.jsonl").write_text(
        "\n".join([
            json.dumps({
                "schema_version": "melix.evaluation_sample.v1",
                "job_id": "eval-1",
                "suite_id": "mmlu",
                "dataset_id": "mmlu.dev.v1",
                "sample_id": "1",
                "question": "2+2?",
                "expected": "4",
                "predicted": "4",
                "raw_response": "4",
                "correct": True,
                "time_s": 0.01,
                "parse_status": "parsed",
            }),
        ]) + "\n"
    )


def _write_eval_compare_fixtures(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "evaluation-compare-job.json").write_text(
        json.dumps({
            "schema_version": "melix.evaluation_compare_job.v1",
            "job_id": "eval-compare-1",
            "base_model_id": "melix-dev-text",
            "target_model_ids": ["melix-dev-text-lora-a"],
            "task_kind": "text-generation",
            "source_repo": "HuggingFaceH4/ultrachat_200k",
            "suite_id": "mmlu",
            "dataset_id": "mmlu.dev.v1",
            "sample_size": 8,
            "scoring_mode": "multiple_choice_accuracy",
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
                    "schema_version": "melix.evaluation_compare_summary.v1",
                    "job_id": "eval-compare-1",
                    "base_model_id": "melix-dev-text",
                    "target_model_id": "melix-dev-text-lora-a",
                    "suite_id": "mmlu",
                    "dataset_id": "mmlu.dev.v1",
                    "sample_size": 8,
                    "scoring_mode": "multiple_choice_accuracy",
                    "win_count": 5,
                    "loss_count": 1,
                    "tie_count": 2,
                    "regression_count": 1,
                    "base_accuracy": 0.5,
                    "target_accuracy": 1.0,
                    "delta_accuracy": 0.5,
                    "duration_seconds": 3.25,
                    "metrics": [
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
                "schema_version": "melix.evaluation_compare_sample.v1",
                "job_id": "eval-compare-1",
                "suite_id": "mmlu",
                "dataset_id": "mmlu.dev.v1",
                "sample_id": "sample-1",
                "target_model_id": "melix-dev-text-lora-a",
                "question": "2+2?",
                "expected": "4",
                "base_predicted": "3",
                "target_predicted": "4",
                "base_raw_response": "3",
                "target_raw_response": "4",
                "base_correct": False,
                "target_correct": True,
                "outcome": "win",
                "regression": False,
                "base_time_s": 0.03,
                "target_time_s": 0.02,
                "base_parse_status": "parsed",
                "target_parse_status": "parsed",
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


def test_collect_evaluation_artifacts_finds_persisted_eval_files(tmp_path: Path) -> None:
    _write_eval_fixtures(tmp_path)

    result = collect_evaluation_artifacts(tmp_path)

    assert len(result["evaluation_jobs"]) == 1
    assert result["evaluation_jobs"][0]["job_id"] == "eval-1"
    assert len(result["evaluation_results"]) == 1
    assert result["evaluation_results"][0]["suite_id"] == "mmlu"
    assert len(result["evaluation_samples"]) == 1
    assert result["evaluation_samples"][0]["sample_id"] == "1"


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
    assert result["evaluation_summary_rows"][0]["score_name"] == "eval.compare.delta_accuracy"
    assert result["evaluation_summary_rows"][0]["score_value"] == 0.5
    assert result["evaluation_samples"][0]["job_id"] == "eval-compare-1"
    assert result["evaluation_samples"][0]["sample_id"] == "melix-dev-text-lora-a:sample-1"
    assert result["evaluation_samples"][0]["predicted"] == "4"


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

    assert "job_id,task_kind,source_repo,model_id,suite_id,context_length" in summary_csv.splitlines()[0]
    assert "job_id,cell_id,task_kind,suite_id,context_length,generation_length" in requests_csv.splitlines()[0]
    assert "bench-matrix-1,text-generation,HuggingFaceH4/ultrachat_200k,melix-dev-text,smoke,1024,128,2,cold,enabled,plain_text,1,3,24,0,24.45,1.2,88.4,3.1,1400.0,58.2,3.8,221.5,1.0,2147483648,5.1,9.2,111" in summary_csv
    assert "bench-matrix-1,cell-1,text-generation,smoke,1024,128,2,cold,enabled,plain_text,1,0,0,24.45,88.4,1400.0,58.2,5.1,2147483648,completed,,111" in requests_csv


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

    summary_lines = [line for line in summary_csv.splitlines() if line.strip()]
    samples_lines = [line for line in samples_csv.splitlines() if line.strip()]
    assert len(summary_lines) == 1
    assert summary_lines[0].startswith("job_id,task_kind")
    assert len(samples_lines) == 1
    assert samples_lines[0].startswith("job_id,suite_id")


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
