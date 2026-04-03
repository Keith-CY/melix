from __future__ import annotations

from worker.productization.benchmark_schemas import (
    build_evaluation_job,
    build_evaluation_result,
    build_serving_benchmark_job,
    build_serving_benchmark_results,
)


def test_build_serving_benchmark_job_preserves_identity_and_parameters() -> None:
    job = build_serving_benchmark_job(
        job_id="bench-123",
        model_id="melix-dev-text",
        task_kind="text-generation",
        source_repo="HuggingFaceH4/ultrachat_200k",
        suites=("smoke", "latency"),
        parameters={"sample_size": "32", "batch_factor": "2"},
        status="completed",
        output_dir="/tmp/melix-bench",
        created_at_unix_ms=101,
        updated_at_unix_ms=202,
    )

    payload = job.to_dict()

    assert payload["schema_version"] == "melix.serving_benchmark_job.v1"
    assert payload["job_id"] == "bench-123"
    assert payload["model_id"] == "melix-dev-text"
    assert payload["task_kind"] == "text-generation"
    assert payload["source_repo"] == "HuggingFaceH4/ultrachat_200k"
    assert payload["suites"] == ["smoke", "latency"]
    assert payload["parameters"] == {"sample_size": "32", "batch_factor": "2"}
    assert payload["status"] == "completed"
    assert payload["output_dir"] == "/tmp/melix-bench"
    assert payload["created_at_unix_ms"] == 101
    assert payload["updated_at_unix_ms"] == 202


def test_build_serving_benchmark_results_groups_metrics_by_suite() -> None:
    results = build_serving_benchmark_results(
        job_id="bench-123",
        metrics={
            "bench.smoke.ttft_ms": 24.45,
            "bench.smoke.tokens_per_second": 47.08,
            "bench.latency.p95_ms": 44.72,
            "bench.summary.job_ms": 88.0,
        },
        units={
            "bench.smoke.ttft_ms": "ms",
            "bench.smoke.tokens_per_second": "tok/s",
            "bench.latency.p95_ms": "ms",
            "bench.summary.job_ms": "ms",
        },
        report_path="/tmp/melix-bench/bench-report.md",
        report_markdown="# Melix Bench\n",
    )

    payload = [result.to_dict() for result in results]

    assert [row["suite"] for row in payload] == ["latency", "smoke", "summary"]
    assert payload[0]["metrics"] == [{"name": "bench.latency.p95_ms", "unit": "ms", "value": 44.72}]
    assert payload[1]["metrics"] == [
        {"name": "bench.smoke.tokens_per_second", "unit": "tok/s", "value": 47.08},
        {"name": "bench.smoke.ttft_ms", "unit": "ms", "value": 24.45},
    ]
    assert payload[2]["metrics"] == [{"name": "bench.summary.job_ms", "unit": "ms", "value": 88.0}]


def test_build_evaluation_job_and_result_remain_distinct_from_serving_shape() -> None:
    job = build_evaluation_job(
        job_id="eval-7",
        model_id="melix-dev-text",
        task_kind="text-generation",
        source_repo="HuggingFaceH4/ultrachat_200k",
        suite_id="mmlu",
        dataset_id="mmlu-dev",
        sample_size=64,
        scoring_mode="exact-match",
        parameters={"split": "validation"},
        status="completed",
        output_dir="/tmp/melix-eval/runs/eval-7",
        created_at_unix_ms=101,
        updated_at_unix_ms=202,
    )
    result = build_evaluation_result(
        job_id="eval-7",
        suite_id="mmlu",
        dataset_id="mmlu-dev",
        sample_size=64,
        metrics={"eval.mmlu.accuracy": 0.72, "eval.mmlu.loss": 0.18},
        report_path="/tmp/melix-eval/mmlu.json",
        units={"eval.mmlu.accuracy": "ratio", "eval.mmlu.loss": "loss"},
    )

    job_payload = job.to_dict()
    result_payload = result.to_dict()

    assert job_payload["schema_version"] == "melix.evaluation_job.v1"
    assert job_payload["task_kind"] == "text-generation"
    assert job_payload["source_repo"] == "HuggingFaceH4/ultrachat_200k"
    assert job_payload["suite_id"] == "mmlu"
    assert job_payload["dataset_id"] == "mmlu-dev"
    assert job_payload["sample_size"] == 64
    assert job_payload["output_dir"] == "/tmp/melix-eval/runs/eval-7"
    assert result_payload["schema_version"] == "melix.evaluation_result.v1"
    assert result_payload["metrics"] == [
        {"name": "eval.mmlu.accuracy", "unit": "ratio", "value": 0.72},
        {"name": "eval.mmlu.loss", "unit": "loss", "value": 0.18},
    ]
