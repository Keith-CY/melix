from __future__ import annotations

from worker.productization.benchmark_schemas import (
    BenchmarkMatrixRequestRow,
    benchmark_matrix_tool_turn_summary_fields,
    build_benchmark_matrix_job,
    build_benchmark_matrix_request_row,
    build_benchmark_matrix_summary_row,
    build_evaluation_job,
    build_evaluation_result,
    build_serving_benchmark_repeat_group_row,
    build_serving_benchmark_request_row,
    build_serving_benchmark_batch_row,
    build_serving_benchmark_context_row,
    build_serving_benchmark_job,
    build_serving_benchmark_results,
)


def _default_speculative_dflash_fields() -> dict[str, object]:
    return {
        "speculative_acceptance_rate": 0.0,
        "speculative_rollback_rate": 0.0,
        "speculative_accepted_tokens": 0,
        "speculative_rejected_tokens": 0,
        "speculative_fallback_count": 0,
        "speculative_num_draft_tokens": 0,
        "speculative_draft_model_configured": False,
        "speculative_draft_propose_ms": 0.0,
        "speculative_target_verify_ms": 0.0,
        "dflash_enabled": False,
        "dflash_block_size": 0,
        "dflash_rollback_count": 0,
        "dflash_target_hidden_layers": 0,
    }


def _default_agentic_benchmark_fields() -> dict[str, object]:
    return {
        "tool_call_count": 0,
        "tool_latency_ms": 0.0,
        "observation_bytes": 0,
        "fatal_rate": 0.0,
        "turn_count": 0,
    }


def _default_request_row_fields() -> dict[str, object]:
    return {
        "job_id": "bench-matrix-1",
        "cell_id": "cell-1",
        "task_kind": "text-generation",
        "suite_id": "agentic",
        "context_length": 64,
        "generation_length": 16,
        "batch_size": 1,
        "cache_profile": "cold",
        "reasoning_mode": "",
        "structured_output_mode": "",
        "concurrency_level": 1,
        "repeat_index": 0,
        "request_index": 0,
        "ttft_ms": 11.2,
        "request_latency_ms": 42.8,
        "prefill_tokens_per_second": 24.5,
        "decode_tokens_per_second": 51.25,
        "queue_wait_ms": 0.0,
        "peak_memory_bytes": 4096,
        "status": "completed",
        "error_code": "",
        "created_at_unix_ms": 101,
    }


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
        "dataset_materialize_ms": 0.0,
        "prompt_render_ms": 0.0,
        "warmup_ms": 0.0,
        "prefill_ms": 0.0,
        "decode_ms": 0.0,
        "tokens_in": 0,
        "tokens_out": 0,
        "first_token_index": 0,
        "cache_hit": False,
        "runtime_kind": "",
        "error_stage": "",
        **_default_speculative_dflash_fields(),
        **_default_agentic_benchmark_fields(),
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
        "dataset_materialize_ms": 0.0,
        "prompt_render_ms": 0.0,
        "warmup_ms": 0.0,
        "prefill_ms": 0.0,
        "decode_ms": 0.0,
        "tokens_in": 0,
        "tokens_out": 0,
        "first_token_index": 0,
        "cache_hit": False,
        "runtime_kind": "",
        "error_stage": "",
        **_default_speculative_dflash_fields(),
        **_default_agentic_benchmark_fields(),
    }


def test_build_serving_benchmark_repeat_group_row_includes_ci_fields() -> None:
    row = build_serving_benchmark_repeat_group_row(
        job_id="bench-123",
        model_id="melix-dev-text",
        task_kind="text-generation",
        source_repo="local",
        suite="smoke",
        context_length=64,
        generation_length=16,
        batch_size=1,
        cache_profile="cold",
        reasoning_mode="",
        structured_output_mode="",
        source_row_kind="context",
        repetition_index=(0, 1, 2),
        sample_count=3,
        seed_strategy="runner_repeat_index",
        throughput_mean=102.0,
        throughput_stdev=2.0,
        throughput_ci95_low=99.7368,
        throughput_ci95_high=104.2632,
        ttft_ms_mean=12.0,
        ttft_ms_stdev=1.0,
        ttft_ms_ci95_low=10.8684,
        ttft_ms_ci95_high=13.1316,
        peak_memory_bytes_mean=2048.0,
        peak_memory_bytes_stdev=16.0,
        peak_memory_bytes_ci95_low=2029.891,
        peak_memory_bytes_ci95_high=2066.109,
        energy_joules_mean=4.2,
        energy_joules_stdev=0.2,
        energy_joules_ci95_low=3.9737,
        energy_joules_ci95_high=4.4263,
    ).to_dict()

    assert row == {
        "schema_version": "melix.serving_benchmark_repeat_group.v1",
        "group_id": "bench-123:context:smoke:64:16:1:cold:::",
        "job_id": "bench-123",
        "model_id": "melix-dev-text",
        "task_kind": "text-generation",
        "source_repo": "local",
        "suite": "smoke",
        "context_length": 64,
        "generation_length": 16,
        "batch_size": 1,
        "cache_profile": "cold",
        "reasoning_mode": "",
        "structured_output_mode": "",
        "source_row_kind": "context",
        "repetition_index": [0, 1, 2],
        "sample_count": 3,
        "seed_strategy": "runner_repeat_index",
        "methodology_version": "melix.benchmark_repeat_group.methodology.v1",
        "throughput_mean": 102.0,
        "throughput_stdev": 2.0,
        "throughput_ci95_low": 99.7368,
        "throughput_ci95_high": 104.2632,
        "ttft_ms_mean": 12.0,
        "ttft_ms_stdev": 1.0,
        "ttft_ms_ci95_low": 10.8684,
        "ttft_ms_ci95_high": 13.1316,
        "request_latency_ms_mean": 0.0,
        "request_latency_ms_stdev": 0.0,
        "request_latency_ms_ci95_low": 0.0,
        "request_latency_ms_ci95_high": 0.0,
        "peak_memory_bytes_mean": 2048.0,
        "peak_memory_bytes_stdev": 16.0,
        "peak_memory_bytes_ci95_low": 2029.891,
        "peak_memory_bytes_ci95_high": 2066.109,
        "energy_joules_mean": 4.2,
        "energy_joules_stdev": 0.2,
        "energy_joules_ci95_low": 3.9737,
        "energy_joules_ci95_high": 4.4263,
    }


def test_build_serving_benchmark_repeat_group_row_omits_absent_optional_energy() -> None:
    row = build_serving_benchmark_repeat_group_row(
        job_id="bench-repeat",
        model_id="melix-dev-text",
        task_kind="text-generation",
        source_repo="local",
        suite="smoke",
        context_length=64,
        generation_length=16,
        batch_size=1,
        cache_profile="cold",
        reasoning_mode="",
        structured_output_mode="",
        source_row_kind="context",
        repetition_index=(0,),
        sample_count=1,
        seed_strategy="runner_repeat_index",
        throughput_mean=100.0,
        throughput_ci95_low=100.0,
        throughput_ci95_high=100.0,
    ).to_dict()

    assert row["sample_count"] == 1
    assert "energy_joules_mean" not in row
    assert "energy_joules_stdev" not in row
    assert "energy_joules_ci95_low" not in row
    assert "energy_joules_ci95_high" not in row


def test_benchmark_rows_preserve_phase_probe_fields() -> None:
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
        dataset_materialize_ms=3.4,
        prompt_render_ms=1.2,
        warmup_ms=4.5,
        prefill_ms=11.2,
        decode_ms=31.6,
        tokens_in=64,
        tokens_out=16,
        first_token_index=1,
        cache_hit=True,
        runtime_kind="text",
        error_stage="",
        speculative_acceptance_rate=0.8,
        speculative_rollback_rate=0.2,
        speculative_accepted_tokens=12,
        speculative_rejected_tokens=3,
        speculative_fallback_count=1,
        speculative_num_draft_tokens=4,
        speculative_draft_model_configured=True,
        speculative_draft_propose_ms=6.7,
        speculative_target_verify_ms=8.9,
        dflash_enabled=True,
        dflash_block_size=16,
        dflash_rollback_count=2,
        dflash_target_hidden_layers=12,
    ).to_dict()
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
        dataset_materialize_ms=2.0,
        prompt_render_ms=1.5,
        warmup_ms=0.0,
        prefill_ms=24.45,
        decode_ms=63.95,
        tokens_in=1024,
        tokens_out=128,
        first_token_index=1,
        cache_hit=False,
        runtime_kind="text",
        error_stage="",
        speculative_acceptance_rate=0.7,
        speculative_rollback_rate=0.3,
        speculative_accepted_tokens=16,
        speculative_rejected_tokens=4,
        speculative_fallback_count=0,
        speculative_num_draft_tokens=5,
        speculative_draft_model_configured=True,
        speculative_draft_propose_ms=7.8,
        speculative_target_verify_ms=9.1,
        dflash_enabled=True,
        dflash_block_size=8,
        dflash_rollback_count=1,
        dflash_target_hidden_layers=10,
    ).to_dict()

    assert context_row["dataset_materialize_ms"] == 3.4
    assert context_row["prompt_render_ms"] == 1.2
    assert context_row["warmup_ms"] == 4.5
    assert context_row["prefill_ms"] == 11.2
    assert context_row["decode_ms"] == 31.6
    assert context_row["tokens_in"] == 64
    assert context_row["tokens_out"] == 16
    assert context_row["first_token_index"] == 1
    assert context_row["cache_hit"] is True
    assert context_row["runtime_kind"] == "text"
    assert context_row["error_stage"] == ""
    assert context_row["speculative_acceptance_rate"] == 0.8
    assert context_row["speculative_accepted_tokens"] == 12
    assert context_row["speculative_draft_model_configured"] is True
    assert context_row["dflash_enabled"] is True
    assert context_row["dflash_block_size"] == 16
    assert request_row["prompt_render_ms"] == 1.5
    assert request_row["tokens_out"] == 128
    assert request_row["speculative_rejected_tokens"] == 4
    assert request_row["dflash_rollback_count"] == 1


def test_benchmark_rows_preserve_agentic_tool_evidence() -> None:
    tool_kwargs = {
        "agentic_tool_registry": {"toolset_version": "melix.agentic_tools.builtin.v1"},
        "agentic_tool_calls": ({"id": "call-1", "name": "visit", "arguments": {"url": "fixture://page"}},),
        "agentic_tool_observations": ({"status": "completed", "payload": {"text": "Visited."}},),
        "agentic_tool_metrics": {
            "agentic_tool.call_count": 1.0,
            "agentic_tool.latency_ms": 12.5,
            "agentic_tool.observation_emitted_bytes": 42.0,
        },
        "tool_call_count": 1,
        "tool_latency_ms": 12.5,
        "observation_bytes": 42,
        "fatal_rate": 0.0,
        "turn_count": 2,
    }
    context_row = build_serving_benchmark_context_row(
        job_id="bench-123",
        model_id="melix-dev-text",
        task_kind="text-generation",
        source_repo="local",
        suite="agentic",
        context_length=64,
        generation_length=16,
        batch_size=1,
        repeat_index=0,
        prefill_tokens_per_second=24.5,
        decode_tokens_per_second=51.25,
        ttft_ms=11.2,
        request_latency_ms=42.8,
        peak_memory_bytes=4096.0,
        speedup_vs_batch_1=1.0,
        cache_profile="cold",
        reasoning_mode="",
        structured_output_mode="",
        **tool_kwargs,
    ).to_dict()
    request_row = build_benchmark_matrix_request_row(
        job_id="bench-matrix-1",
        cell_id="cell-1",
        task_kind="text-generation",
        suite_id="agentic",
        context_length=64,
        generation_length=16,
        batch_size=1,
        cache_profile="cold",
        reasoning_mode="",
        structured_output_mode="",
        concurrency_level=1,
        repeat_index=0,
        request_index=0,
        ttft_ms=11.2,
        request_latency_ms=42.8,
        prefill_tokens_per_second=24.5,
        decode_tokens_per_second=51.25,
        queue_wait_ms=0.0,
        peak_memory_bytes=4096,
        status="completed",
        error_code="",
        created_at_unix_ms=101,
        **tool_kwargs,
    ).to_dict()

    assert context_row["agentic_tool_registry"]["toolset_version"] == "melix.agentic_tools.builtin.v1"
    assert context_row["agentic_tool_calls"][0]["name"] == "visit"
    assert context_row["tool_call_count"] == 1
    assert context_row["tool_latency_ms"] == 12.5
    assert context_row["observation_bytes"] == 42
    assert context_row["fatal_rate"] == 0.0
    assert context_row["turn_count"] == 2
    assert request_row["agentic_tool_observations"][0]["payload"]["text"] == "Visited."
    assert request_row["agentic_tool_metrics"]["agentic_tool.call_count"] == 1.0
    assert request_row["tool_call_count"] == 1


def test_benchmark_rows_derive_tool_turn_fields_from_agentic_metrics() -> None:
    tool_metrics = {
        "agentic_tool.call_count": 2.0,
        "agentic_tool.latency_ms": 15.25,
        "agentic_tool.observation_count": 2.0,
        "agentic_tool.observation_emitted_bytes": 128.0,
        "agentic_tool.timeout_count": 1.0,
        "agentic_tool.failed_count": 0.0,
    }

    context_row = build_serving_benchmark_context_row(
        job_id="bench-123",
        model_id="melix-dev-text",
        task_kind="text-generation",
        source_repo="local",
        suite="agentic",
        context_length=64,
        generation_length=16,
        batch_size=1,
        repeat_index=0,
        prefill_tokens_per_second=24.5,
        decode_tokens_per_second=51.25,
        ttft_ms=11.2,
        request_latency_ms=42.8,
        peak_memory_bytes=4096.0,
        speedup_vs_batch_1=1.0,
        cache_profile="cold",
        reasoning_mode="",
        structured_output_mode="",
        agentic_tool_metrics=tool_metrics,
    ).to_dict()
    request_row = build_benchmark_matrix_request_row(
        **_default_request_row_fields(),
        agentic_tool_metrics=tool_metrics,
    ).to_dict()

    assert context_row["tool_call_count"] == 2
    assert context_row["tool_latency_ms"] == 15.25
    assert context_row["observation_bytes"] == 128
    assert context_row["fatal_rate"] == 1.0
    assert context_row["turn_count"] == 4
    assert request_row["tool_call_count"] == 2
    assert request_row["fatal_rate"] == 1.0


def test_benchmark_rows_preserve_explicit_tool_turn_fields_and_tolerate_bad_metrics() -> None:
    request_row = build_benchmark_matrix_request_row(
        **_default_request_row_fields(),
        agentic_tool_metrics={
            "agentic_tool.call_count": object(),  # type: ignore[dict-item]
            "agentic_tool.observation_count": "bad",  # type: ignore[dict-item]
        },
        tool_call_count=3,
        tool_latency_ms=4.5,
        observation_bytes=64,
        fatal_rate=0.25,
        turn_count=7,
    ).to_dict()
    batch_row = build_serving_benchmark_batch_row(
        job_id="bench-123",
        model_id="melix-dev-text",
        task_kind="text-generation",
        source_repo="local",
        suite="agentic",
        context_length=64,
        generation_length=16,
        batch_size=2,
        repeat_index=0,
        prefill_tokens_per_second=24.5,
        decode_tokens_per_second=51.25,
        ttft_ms=11.2,
        request_latency_ms=42.8,
        peak_memory_bytes=4096.0,
        speedup_vs_batch_1=1.0,
        cache_profile="cold",
        reasoning_mode="",
        structured_output_mode="",
        agentic_tool_metrics={"agentic_tool.call_count": 1.0},
    ).to_dict()

    assert request_row["tool_call_count"] == 3
    assert request_row["tool_latency_ms"] == 4.5
    assert request_row["observation_bytes"] == 64
    assert request_row["fatal_rate"] == 0.25
    assert request_row["turn_count"] == 7
    assert batch_row["tool_call_count"] == 1


def test_serving_benchmark_request_rows_preserve_tool_turn_and_final_answer_phases() -> None:
    tool_turn = build_serving_benchmark_request_row(
        job_id="bench-123",
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
        duration_ms=12.5,
        dataset_materialize_ms=3.0,
        prompt_render_ms=2.0,
        tool_call_id="visit-1",
        tool_name="visit",
        tool_arguments={"url": "fixture://page"},
        tool_observation={"status": "completed", "payload": {"text": "Visited."}},
        agentic_tool_metrics={
            "agentic_tool.call_count": 1.0,
            "agentic_tool.latency_ms": 12.5,
            "agentic_tool.observation_count": 1.0,
            "agentic_tool.observation_emitted_bytes": 42.0,
        },
        created_at_unix_ms=101,
    ).to_dict()
    final_answer = build_serving_benchmark_request_row(
        job_id="bench-123",
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
        ttft_ms=11.2,
        request_latency_ms=42.8,
        prefill_tokens_per_second=24.5,
        decode_tokens_per_second=51.25,
        peak_memory_bytes=4096,
        prefill_ms=11.2,
        decode_ms=31.6,
        tokens_in=64,
        tokens_out=16,
        first_token_index=1,
        runtime_kind="text",
        tool_call_count=1,
        tool_latency_ms=12.5,
        observation_bytes=42,
        turn_count=2,
        created_at_unix_ms=102,
    ).to_dict()

    assert tool_turn == {
        "schema_version": "melix.serving_benchmark_request_row.v1",
        "job_id": "bench-123",
        "model_id": "melix-dev-text",
        "task_kind": "text-generation",
        "source_repo": "local",
        "suite": "agentic_visit",
        "context_length": 64,
        "generation_length": 16,
        "batch_size": 1,
        "repeat_index": 0,
        "request_index": 0,
        "phase": "tool_turn",
        "phase_index": 0,
        "status": "completed",
        "error_code": "",
        "error_stage": "",
        "duration_ms": 12.5,
        "ttft_ms": 0.0,
        "request_latency_ms": 0.0,
        "prefill_tokens_per_second": 0.0,
        "decode_tokens_per_second": 0.0,
        "peak_memory_bytes": 0.0,
        "dataset_materialize_ms": 3.0,
        "prompt_render_ms": 2.0,
        "warmup_ms": 0.0,
        "prefill_ms": 0.0,
        "decode_ms": 0.0,
        "tokens_in": 0,
        "tokens_out": 0,
        "first_token_index": 0,
        "cache_hit": False,
        "runtime_kind": "",
        "tool_call_id": "visit-1",
        "tool_name": "visit",
        "tool_arguments_json": '{"url":"fixture://page"}',
        "tool_observation_json": '{"payload":{"text":"Visited."},"status":"completed"}',
        "tool_call_count": 1,
        "tool_latency_ms": 12.5,
        "observation_bytes": 42,
        "fatal_rate": 0.0,
        "turn_count": 2,
        "compare_target_kind": "base",
        "base_model_id": "melix-dev-text",
        "adapter_manifest_path": "",
        "adapter_set_hash": "",
        "adapter_activation_mode": "",
        "created_at_unix_ms": 101,
    }
    assert final_answer["phase"] == "final_answer"
    assert final_answer["tool_call_id"] == ""
    assert final_answer["tool_call_count"] == 1
    assert final_answer["tokens_out"] == 16


def test_serving_benchmark_request_rows_preserve_adapter_compare_identity() -> None:
    row = build_serving_benchmark_request_row(
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
        compare_target_kind="adapter",
        base_model_id="melix-dev-text",
        adapter_manifest_path="/tmp/melix/train_lora.adapter.json",
        adapter_set_hash="deadbeefcafebabe",
        adapter_activation_mode="adapter_backed_runtime",
    ).to_dict()

    assert row["compare_target_kind"] == "adapter"
    assert row["base_model_id"] == "melix-dev-text"
    assert row["adapter_manifest_path"] == "/tmp/melix/train_lora.adapter.json"
    assert row["adapter_set_hash"] == "deadbeefcafebabe"
    assert row["adapter_activation_mode"] == "adapter_backed_runtime"
    assert row["tool_call_count"] == 1
    assert row["tool_latency_ms"] == 5.5


def test_benchmark_matrix_tool_turn_summary_fields_aggregate_requests() -> None:
    rows: tuple[BenchmarkMatrixRequestRow, ...] = (
        build_benchmark_matrix_request_row(
            **_default_request_row_fields(),
            agentic_tool_metrics={
                "agentic_tool.call_count": 1.0,
                "agentic_tool.latency_ms": 2.5,
                "agentic_tool.observation_count": 1.0,
                "agentic_tool.observation_emitted_bytes": 40.0,
            },
        ),
        build_benchmark_matrix_request_row(
            **{
                **_default_request_row_fields(),
                "request_index": 1,
            },
            agentic_tool_metrics={
                "agentic_tool.call_count": 1.0,
                "agentic_tool.latency_ms": 3.25,
                "agentic_tool.observation_count": 1.0,
                "agentic_tool.observation_emitted_bytes": 88.0,
                "agentic_tool.timeout_count": 1.0,
            },
        ),
    )

    assert benchmark_matrix_tool_turn_summary_fields(rows) == {
        "tool_call_count": 2,
        "tool_latency_ms": 5.75,
        "observation_bytes": 128,
        "fatal_rate": 0.5,
        "turn_count": 4,
    }


def test_benchmark_job_and_rows_preserve_trajectory_provenance() -> None:
    provenance = {
        "trajectory_dataset_id": "opensearch-vl.dev",
        "trajectory_dataset_version": "2026-05-19",
        "trajectory_schema_version": "melix.agentic_tool_trace.v1",
        "trajectory_snapshot_manifest_path": "/tmp/run/normalized_dataset/manifest.json",
        "trajectory_split": "train",
        "trajectory_trace_digest": "abc123",
        "trajectory_toolset_version": "melix.agentic_tools.builtin.v1",
        "trajectory_reward_policy_id": "reward-policy.v1",
        "trajectory_quality_metrics": {"agentic_trace_count": 1},
    }
    job = build_serving_benchmark_job(
        job_id="bench-123",
        model_id="melix-dev-text",
        source_repo="local",
        suites=("agentic",),
        parameters={},
        status="completed",
        output_dir="/tmp/bench",
        trajectory_provenance=provenance,
    ).to_dict()
    context_row = build_serving_benchmark_context_row(
        job_id="bench-123",
        model_id="melix-dev-text",
        task_kind="text-generation",
        source_repo="local",
        suite="agentic",
        context_length=64,
        generation_length=16,
        batch_size=1,
        repeat_index=0,
        prefill_tokens_per_second=24.5,
        decode_tokens_per_second=51.25,
        ttft_ms=11.2,
        request_latency_ms=42.8,
        peak_memory_bytes=4096.0,
        speedup_vs_batch_1=1.0,
        cache_profile="cold",
        reasoning_mode="",
        structured_output_mode="",
        trajectory_provenance=provenance,
    ).to_dict()

    assert job["trajectory_dataset_id"] == "opensearch-vl.dev"
    assert context_row["trajectory_trace_digest"] == "abc123"
    assert context_row["trajectory_split"] == "train"
    assert context_row["trajectory_quality_metrics"]["agentic_trace_count"] == 1


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
        cell_wall_ms=353.6,
        completed_count=4,
        failed_count=0,
        ttft_p50_ms=24.45,
        ttft_p95_ms=25.0,
        request_latency_p50_ms=88.4,
        request_latency_p95_ms=90.0,
        tool_call_count=3,
        tool_latency_ms=18.5,
        observation_bytes=128,
        fatal_rate=0.25,
        turn_count=6,
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
        "parameters": {},
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
        "cell_wall_ms": 353.6,
        "completed_count": 4,
        "failed_count": 0,
        "ttft_p50_ms": 24.45,
        "ttft_p95_ms": 25.0,
        "request_latency_p50_ms": 88.4,
        "request_latency_p95_ms": 90.0,
        "tool_call_count": 3,
        "tool_latency_ms": 18.5,
        "observation_bytes": 128,
        "fatal_rate": 0.25,
        "turn_count": 6,
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
        "dataset_materialize_ms": 0.0,
        "prompt_render_ms": 0.0,
        "warmup_ms": 0.0,
        "prefill_ms": 0.0,
        "decode_ms": 0.0,
        "tokens_in": 0,
        "tokens_out": 0,
        "first_token_index": 0,
        "cache_hit": False,
        "runtime_kind": "",
        "error_stage": "",
        **_default_speculative_dflash_fields(),
        **_default_agentic_benchmark_fields(),
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
