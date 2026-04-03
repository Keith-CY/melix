from __future__ import annotations

import json
from pathlib import Path

from worker.productization.benchmark_export import (
    build_comparison_table,
    build_export_bundle,
    collect_benchmark_artifacts,
    collect_evaluation_artifacts,
    write_export_bundle,
)


def _write_bench_fixtures(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "bench-job.json").write_text(
        json.dumps({
            "schema_version": "melix.serving_benchmark_job.v1",
            "job_id": "bench-1",
            "model_id": "melix-dev-text",
            "suites": ["smoke"],
            "parameters": {},
            "status": "completed",
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
    (run_root / "bench-job.json").write_text(
        json.dumps({
            "schema_version": "melix.serving_benchmark_job.v1",
            "job_id": job_id,
            "model_id": model_id,
            "suites": ["smoke"],
            "parameters": {"sample_size": "4"},
            "status": "completed",
            "output_dir": str(run_root),
            "created_at_unix_ms": 101,
            "updated_at_unix_ms": 202,
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


def test_collect_benchmark_artifacts_finds_persisted_bench_files(tmp_path: Path) -> None:
    _write_bench_fixtures(tmp_path)

    result = collect_benchmark_artifacts(tmp_path)

    assert len(result["benchmark_jobs"]) == 1
    assert result["benchmark_jobs"][0]["job_id"] == "bench-1"
    assert len(result["benchmark_results"]) == 1
    assert result["benchmark_results"][0]["suite"] == "smoke"


def test_collect_benchmark_artifacts_reads_per_run_history_from_runs_directory(
    tmp_path: Path,
) -> None:
    bench_root = tmp_path / "bench"
    _write_bench_run_fixture(bench_root, job_id="bench-1", model_id="model-a", ttft_ms=11.0)
    _write_bench_run_fixture(bench_root, job_id="bench-2", model_id="model-b", ttft_ms=13.5)

    result = collect_benchmark_artifacts(tmp_path)

    assert [job["job_id"] for job in result["benchmark_jobs"]] == ["bench-1", "bench-2"]
    assert [row["job_id"] for row in result["benchmark_results"]] == ["bench-1", "bench-2"]


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


def test_build_export_bundle_combines_benchmark_and_evaluation_artifacts(tmp_path: Path) -> None:
    _write_bench_fixtures(tmp_path)
    _write_eval_fixtures(tmp_path)

    bundle = build_export_bundle(tmp_path)

    assert bundle["export_schema_version"] == "melix.benchmark_export.v1"
    assert isinstance(bundle["exported_at_unix_ms"], int)
    assert len(bundle["benchmark_jobs"]) == 1
    assert len(bundle["evaluation_jobs"]) == 1
    assert len(bundle["evaluation_samples"]) == 1


def test_build_export_bundle_collects_benchmark_and_evaluation_from_model_ops_root(
    tmp_path: Path,
) -> None:
    jobs_root = tmp_path / "model-ops"
    _write_bench_fixtures(jobs_root / "bench")
    _write_eval_fixtures(jobs_root / "evaluation")

    bundle = build_export_bundle(jobs_root)

    assert len(bundle["benchmark_jobs"]) == 1
    assert len(bundle["benchmark_results"]) == 1
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
