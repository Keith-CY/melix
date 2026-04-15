from __future__ import annotations

from worker.productization.benchmark_schemas import (
    build_benchmark_matrix_job,
    build_benchmark_matrix_request_row,
    build_benchmark_matrix_summary_row,
    build_evaluation_job,
    build_evaluation_result,
    build_serving_benchmark_batch_row,
    build_serving_benchmark_context_row,
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
        context_lengths=(32, 64),
        generation_length=16,
        batch_sizes=(1, 2),
        repeats=3,
        cache_profile="partial_prefix",
        reasoning_mode="step-by-step",
        structured_output_mode="json",
        request_p50_ms=12.5,
        request_p95_ms=19.75,
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
    assert payload["context_lengths"] == [32, 64]
    assert payload["generation_length"] == 16
    assert payload["batch_sizes"] == [1, 2]
    assert payload["repeats"] == 3
    assert payload["cache_profile"] == "partial_prefix"
    assert payload["reasoning_mode"] == "step-by-step"
    assert payload["structured_output_mode"] == "json"
    assert payload["request_p50_ms"] == 12.5
    assert payload["request_p95_ms"] == 19.75
    assert payload["parameters"] == {"sample_size": "32", "batch_factor": "2"}
    assert payload["status"] == "completed"
    assert payload["output_dir"] == "/tmp/melix-bench"
    assert payload["created_at_unix_ms"] == 101
    assert payload["updated_at_unix_ms"] == 202


def test_build_serving_benchmark_context_and_batch_rows_include_canonical_fields() -> None:
    context_row = build_serving_benchmark_context_row(
        job_id="bench-123",
        model_id="melix-dev-text",
        task_kind="text-generation",
        source_repo="HuggingFaceH4/ultrachat_200k",
        suite="smoke",
        context_length=64,
        generation_length=16,
        batch_size=1,
        repeat_index=2,
        prefill_tokens_per_second=24.5,
        decode_tokens_per_second=51.25,
        ttft_ms=11.2,
        request_latency_ms=42.8,
        peak_memory_bytes=4096.0,
        speedup_vs_batch_1=1.0,
        cache_profile="partial_prefix",
        reasoning_mode="step-by-step",
        structured_output_mode="json",
    ).to_dict()
    batch_row = build_serving_benchmark_batch_row(
        job_id="bench-123",
        model_id="melix-dev-text",
        task_kind="text-generation",
        source_repo="HuggingFaceH4/ultrachat_200k",
        suite="smoke",
        context_length=64,
        generation_length=16,
        batch_size=4,
        repeat_index=2,
        prefill_tokens_per_second=25.5,
        decode_tokens_per_second=54.25,
        ttft_ms=10.2,
        request_latency_ms=39.8,
        peak_memory_bytes=4096.0,
        speedup_vs_batch_1=1.08,
        cache_profile="partial_prefix",
        reasoning_mode="step-by-step",
        structured_output_mode="json",
    ).to_dict()

    assert context_row == {
        "schema_version": "melix.serving_benchmark_context_row.v1",
        "job_id": "bench-123",
        "model_id": "melix-dev-text",
        "task_kind": "text-generation",
        "source_repo": "HuggingFaceH4/ultrachat_200k",
        "suite": "smoke",
        "context_length": 64,
        "generation_length": 16,
        "batch_size": 1,
        "repeat_index": 2,
        "prefill_tokens_per_second": 24.5,
        "decode_tokens_per_second": 51.25,
        "ttft_ms": 11.2,
        "request_latency_ms": 42.8,
        "peak_memory_bytes": 4096.0,
        "speedup_vs_batch_1": 1.0,
        "cache_profile": "partial_prefix",
        "reasoning_mode": "step-by-step",
        "structured_output_mode": "json",
    }
    assert batch_row == {
        "schema_version": "melix.serving_benchmark_batch_row.v1",
        "job_id": "bench-123",
        "model_id": "melix-dev-text",
        "task_kind": "text-generation",
        "source_repo": "HuggingFaceH4/ultrachat_200k",
        "suite": "smoke",
        "context_length": 64,
        "generation_length": 16,
        "batch_size": 4,
        "repeat_index": 2,
        "prefill_tokens_per_second": 25.5,
        "decode_tokens_per_second": 54.25,
        "ttft_ms": 10.2,
        "request_latency_ms": 39.8,
        "peak_memory_bytes": 4096.0,
        "speedup_vs_batch_1": 1.08,
        "cache_profile": "partial_prefix",
        "reasoning_mode": "step-by-step",
        "structured_output_mode": "json",
    }


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


def test_build_benchmark_matrix_job_and_rows_preserve_canonical_fields() -> None:
    job = build_benchmark_matrix_job(
        job_id="bench-matrix-1",
        model_id="melix-dev-text",
        task_kind="text-generation",
        source_repo="HuggingFaceH4/ultrachat_200k",
        suite_ids=("smoke", "latency"),
        status="completed",
        output_dir="/tmp/melix/bench/matrix-runs/bench-matrix-1",
        created_at_unix_ms=101,
        updated_at_unix_ms=202,
    )
    summary_row = build_benchmark_matrix_summary_row(
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
    )
    request_row = build_benchmark_matrix_request_row(
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
    )

    assert job.to_dict() == {
        "schema_version": "melix.benchmark_matrix_job.v1",
        "job_id": "bench-matrix-1",
        "model_id": "melix-dev-text",
        "task_kind": "text-generation",
        "source_repo": "HuggingFaceH4/ultrachat_200k",
        "suite_ids": ["smoke", "latency"],
        "benchmark_mode": "matrix",
        "status": "completed",
        "output_dir": "/tmp/melix/bench/matrix-runs/bench-matrix-1",
        "created_at_unix_ms": 101,
        "updated_at_unix_ms": 202,
    }
    assert summary_row.to_dict() == {
        "job_id": "bench-matrix-1",
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
    assert request_row.to_dict() == {
        "job_id": "bench-matrix-1",
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
        metrics={"eval.mmlu.threshold_pass_rate": 0.72, "eval.mmlu.typed_score_mean": 0.18},
        report_path="/tmp/melix-eval/mmlu.json",
        units={"eval.mmlu.threshold_pass_rate": "ratio", "eval.mmlu.typed_score_mean": "ratio"},
    )

    job_payload = job.to_dict()
    result_payload = result.to_dict()

    assert job_payload["schema_version"] == "melix.evaluation_job.v2"
    assert job_payload["task_kind"] == "text-generation"
    assert job_payload["source_repo"] == "HuggingFaceH4/ultrachat_200k"
    assert job_payload["suite_id"] == "mmlu"
    assert job_payload["dataset_id"] == "mmlu-dev"
    assert job_payload["sample_size"] == 64
    assert job_payload["output_dir"] == "/tmp/melix-eval/runs/eval-7"
    assert result_payload["schema_version"] == "melix.evaluation_result.v2"
    assert result_payload["metrics"] == [
        {"name": "eval.mmlu.threshold_pass_rate", "unit": "ratio", "value": 0.72},
        {"name": "eval.mmlu.typed_score_mean", "unit": "ratio", "value": 0.18},
    ]
