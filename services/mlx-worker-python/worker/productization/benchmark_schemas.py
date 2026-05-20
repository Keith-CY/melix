from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import json

from worker.productization.evaluation_schemas import (
    EvaluationJob,
    EvaluationResult,
    EvaluationSample,
    build_evaluation_job_record,
    build_evaluation_result_record,
    build_evaluation_sample_record,
)
from worker.trajectory_provenance import append_trajectory_provenance


_SERVING_BENCHMARK_JOB_SCHEMA_VERSION = "melix.serving_benchmark_job.v1"
_SERVING_BENCHMARK_RESULT_SCHEMA_VERSION = "melix.serving_benchmark_result.v1"
_SERVING_BENCHMARK_REQUEST_ROW_SCHEMA_VERSION = "melix.serving_benchmark_request_row.v1"
_BENCHMARK_MATRIX_JOB_SCHEMA_VERSION = "melix.benchmark_matrix_job.v1"


_AGENTIC_TOOL_CALL_COUNT_KEY = "agentic_tool.call_count"
_AGENTIC_TOOL_LATENCY_MS_KEY = "agentic_tool.latency_ms"
_AGENTIC_TOOL_OBSERVATION_COUNT_KEY = "agentic_tool.observation_count"
_AGENTIC_TOOL_OBSERVATION_BYTES_KEY = "agentic_tool.observation_emitted_bytes"
_AGENTIC_TOOL_TIMEOUT_COUNT_KEY = "agentic_tool.timeout_count"
_AGENTIC_TOOL_FAILED_COUNT_KEY = "agentic_tool.failed_count"


_COMPACT_JSON_KWARGS = {
    "ensure_ascii": False,
    "separators": (",", ":"),
    "sort_keys": True,
}


@dataclass(frozen=True)
class BenchmarkMetricValue:
    name: str
    value: float
    unit: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
        }


@dataclass(frozen=True)
class ServingBenchmarkJob:
    schema_version: str
    job_id: str
    model_id: str
    task_kind: str
    source_repo: str
    suites: tuple[str, ...]
    context_lengths: tuple[int, ...]
    generation_length: int
    batch_sizes: tuple[int, ...]
    repeats: int
    cache_profile: str
    reasoning_mode: str
    structured_output_mode: str
    request_p50_ms: float
    request_p95_ms: float
    parameters: dict[str, str]
    status: str
    output_dir: str
    created_at_unix_ms: int
    updated_at_unix_ms: int
    suite_metadata: dict[str, dict[str, object]] = field(default_factory=dict)
    trajectory_provenance: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "model_id": self.model_id,
            "task_kind": self.task_kind,
            "source_repo": self.source_repo,
            "suites": list(self.suites),
            "context_lengths": list(self.context_lengths),
            "generation_length": self.generation_length,
            "batch_sizes": list(self.batch_sizes),
            "repeats": self.repeats,
            "cache_profile": self.cache_profile,
            "reasoning_mode": self.reasoning_mode,
            "structured_output_mode": self.structured_output_mode,
            "request_p50_ms": self.request_p50_ms,
            "request_p95_ms": self.request_p95_ms,
            "parameters": dict(self.parameters),
            "status": self.status,
            "output_dir": self.output_dir,
            "created_at_unix_ms": self.created_at_unix_ms,
            "updated_at_unix_ms": self.updated_at_unix_ms,
        }
        if self.suite_metadata:
            payload["suite_metadata"] = {
                suite_id: dict(metadata)
                for suite_id, metadata in self.suite_metadata.items()
            }
        append_trajectory_provenance(payload, self.trajectory_provenance)
        return payload


@dataclass(frozen=True)
class ServingBenchmarkContextRow:
    schema_version: str
    job_id: str
    model_id: str
    task_kind: str
    source_repo: str
    suite: str
    context_length: int
    generation_length: int
    batch_size: int
    repeat_index: int
    prefill_tokens_per_second: float
    decode_tokens_per_second: float
    ttft_ms: float
    request_latency_ms: float
    peak_memory_bytes: float
    speedup_vs_batch_1: float
    cache_profile: str
    reasoning_mode: str
    structured_output_mode: str
    dataset_materialize_ms: float = 0.0
    prompt_render_ms: float = 0.0
    warmup_ms: float = 0.0
    prefill_ms: float = 0.0
    decode_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    first_token_index: int = 0
    cache_hit: bool = False
    runtime_kind: str = ""
    error_stage: str = ""
    speculative_acceptance_rate: float = 0.0
    speculative_rollback_rate: float = 0.0
    speculative_accepted_tokens: int = 0
    speculative_rejected_tokens: int = 0
    speculative_fallback_count: int = 0
    speculative_num_draft_tokens: int = 0
    speculative_draft_model_configured: bool = False
    speculative_draft_propose_ms: float = 0.0
    speculative_target_verify_ms: float = 0.0
    dflash_enabled: bool = False
    dflash_block_size: int = 0
    dflash_rollback_count: int = 0
    dflash_target_hidden_layers: int = 0
    tool_call_count: int = 0
    tool_latency_ms: float = 0.0
    observation_bytes: int = 0
    fatal_rate: float = 0.0
    turn_count: int = 0
    agentic_tool_registry: dict[str, object] | None = None
    agentic_tool_calls: tuple[dict[str, object], ...] = ()
    agentic_tool_observations: tuple[dict[str, object], ...] = ()
    agentic_tool_metrics: dict[str, float] | None = None
    trajectory_provenance: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "model_id": self.model_id,
            "task_kind": self.task_kind,
            "source_repo": self.source_repo,
            "suite": self.suite,
            "context_length": self.context_length,
            "generation_length": self.generation_length,
            "batch_size": self.batch_size,
            "repeat_index": self.repeat_index,
            "prefill_tokens_per_second": self.prefill_tokens_per_second,
            "decode_tokens_per_second": self.decode_tokens_per_second,
            "ttft_ms": self.ttft_ms,
            "request_latency_ms": self.request_latency_ms,
            "peak_memory_bytes": self.peak_memory_bytes,
            "speedup_vs_batch_1": self.speedup_vs_batch_1,
            "cache_profile": self.cache_profile,
            "reasoning_mode": self.reasoning_mode,
            "structured_output_mode": self.structured_output_mode,
            "dataset_materialize_ms": self.dataset_materialize_ms,
            "prompt_render_ms": self.prompt_render_ms,
            "warmup_ms": self.warmup_ms,
            "prefill_ms": self.prefill_ms,
            "decode_ms": self.decode_ms,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "first_token_index": self.first_token_index,
            "cache_hit": self.cache_hit,
            "runtime_kind": self.runtime_kind,
            "error_stage": self.error_stage,
            "speculative_acceptance_rate": self.speculative_acceptance_rate,
            "speculative_rollback_rate": self.speculative_rollback_rate,
            "speculative_accepted_tokens": self.speculative_accepted_tokens,
            "speculative_rejected_tokens": self.speculative_rejected_tokens,
            "speculative_fallback_count": self.speculative_fallback_count,
            "speculative_num_draft_tokens": self.speculative_num_draft_tokens,
            "speculative_draft_model_configured": self.speculative_draft_model_configured,
            "speculative_draft_propose_ms": self.speculative_draft_propose_ms,
            "speculative_target_verify_ms": self.speculative_target_verify_ms,
            "dflash_enabled": self.dflash_enabled,
            "dflash_block_size": self.dflash_block_size,
            "dflash_rollback_count": self.dflash_rollback_count,
            "dflash_target_hidden_layers": self.dflash_target_hidden_layers,
            "tool_call_count": self.tool_call_count,
            "tool_latency_ms": self.tool_latency_ms,
            "observation_bytes": self.observation_bytes,
            "fatal_rate": self.fatal_rate,
            "turn_count": self.turn_count,
        }
        _append_agentic_tool_evidence(
            payload,
            registry=self.agentic_tool_registry,
            calls=self.agentic_tool_calls,
            observations=self.agentic_tool_observations,
            metrics=self.agentic_tool_metrics,
        )
        append_trajectory_provenance(payload, self.trajectory_provenance)
        return payload


@dataclass(frozen=True)
class ServingBenchmarkBatchRow:
    schema_version: str
    job_id: str
    model_id: str
    task_kind: str
    source_repo: str
    suite: str
    context_length: int
    generation_length: int
    batch_size: int
    repeat_index: int
    prefill_tokens_per_second: float
    decode_tokens_per_second: float
    ttft_ms: float
    request_latency_ms: float
    peak_memory_bytes: float
    speedup_vs_batch_1: float
    cache_profile: str
    reasoning_mode: str
    structured_output_mode: str
    dataset_materialize_ms: float = 0.0
    prompt_render_ms: float = 0.0
    warmup_ms: float = 0.0
    prefill_ms: float = 0.0
    decode_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    first_token_index: int = 0
    cache_hit: bool = False
    runtime_kind: str = ""
    error_stage: str = ""
    speculative_acceptance_rate: float = 0.0
    speculative_rollback_rate: float = 0.0
    speculative_accepted_tokens: int = 0
    speculative_rejected_tokens: int = 0
    speculative_fallback_count: int = 0
    speculative_num_draft_tokens: int = 0
    speculative_draft_model_configured: bool = False
    speculative_draft_propose_ms: float = 0.0
    speculative_target_verify_ms: float = 0.0
    dflash_enabled: bool = False
    dflash_block_size: int = 0
    dflash_rollback_count: int = 0
    dflash_target_hidden_layers: int = 0
    tool_call_count: int = 0
    tool_latency_ms: float = 0.0
    observation_bytes: int = 0
    fatal_rate: float = 0.0
    turn_count: int = 0
    agentic_tool_registry: dict[str, object] | None = None
    agentic_tool_calls: tuple[dict[str, object], ...] = ()
    agentic_tool_observations: tuple[dict[str, object], ...] = ()
    agentic_tool_metrics: dict[str, float] | None = None
    trajectory_provenance: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "model_id": self.model_id,
            "task_kind": self.task_kind,
            "source_repo": self.source_repo,
            "suite": self.suite,
            "context_length": self.context_length,
            "generation_length": self.generation_length,
            "batch_size": self.batch_size,
            "repeat_index": self.repeat_index,
            "prefill_tokens_per_second": self.prefill_tokens_per_second,
            "decode_tokens_per_second": self.decode_tokens_per_second,
            "ttft_ms": self.ttft_ms,
            "request_latency_ms": self.request_latency_ms,
            "peak_memory_bytes": self.peak_memory_bytes,
            "speedup_vs_batch_1": self.speedup_vs_batch_1,
            "cache_profile": self.cache_profile,
            "reasoning_mode": self.reasoning_mode,
            "structured_output_mode": self.structured_output_mode,
            "dataset_materialize_ms": self.dataset_materialize_ms,
            "prompt_render_ms": self.prompt_render_ms,
            "warmup_ms": self.warmup_ms,
            "prefill_ms": self.prefill_ms,
            "decode_ms": self.decode_ms,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "first_token_index": self.first_token_index,
            "cache_hit": self.cache_hit,
            "runtime_kind": self.runtime_kind,
            "error_stage": self.error_stage,
            "speculative_acceptance_rate": self.speculative_acceptance_rate,
            "speculative_rollback_rate": self.speculative_rollback_rate,
            "speculative_accepted_tokens": self.speculative_accepted_tokens,
            "speculative_rejected_tokens": self.speculative_rejected_tokens,
            "speculative_fallback_count": self.speculative_fallback_count,
            "speculative_num_draft_tokens": self.speculative_num_draft_tokens,
            "speculative_draft_model_configured": self.speculative_draft_model_configured,
            "speculative_draft_propose_ms": self.speculative_draft_propose_ms,
            "speculative_target_verify_ms": self.speculative_target_verify_ms,
            "dflash_enabled": self.dflash_enabled,
            "dflash_block_size": self.dflash_block_size,
            "dflash_rollback_count": self.dflash_rollback_count,
            "dflash_target_hidden_layers": self.dflash_target_hidden_layers,
            "tool_call_count": self.tool_call_count,
            "tool_latency_ms": self.tool_latency_ms,
            "observation_bytes": self.observation_bytes,
            "fatal_rate": self.fatal_rate,
            "turn_count": self.turn_count,
        }
        _append_agentic_tool_evidence(
            payload,
            registry=self.agentic_tool_registry,
            calls=self.agentic_tool_calls,
            observations=self.agentic_tool_observations,
            metrics=self.agentic_tool_metrics,
        )
        append_trajectory_provenance(payload, self.trajectory_provenance)
        return payload


@dataclass(frozen=True)
class ServingBenchmarkRequestRow:
    schema_version: str
    job_id: str
    model_id: str
    task_kind: str
    source_repo: str
    suite: str
    context_length: int
    generation_length: int
    batch_size: int
    repeat_index: int
    request_index: int
    phase: str
    phase_index: int
    status: str
    error_code: str = ""
    error_stage: str = ""
    duration_ms: float = 0.0
    ttft_ms: float = 0.0
    request_latency_ms: float = 0.0
    prefill_tokens_per_second: float = 0.0
    decode_tokens_per_second: float = 0.0
    peak_memory_bytes: float = 0.0
    dataset_materialize_ms: float = 0.0
    prompt_render_ms: float = 0.0
    warmup_ms: float = 0.0
    prefill_ms: float = 0.0
    decode_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    first_token_index: int = 0
    cache_hit: bool = False
    runtime_kind: str = ""
    tool_call_id: str = ""
    tool_name: str = ""
    tool_arguments_json: str = ""
    tool_observation_json: str = ""
    tool_call_count: int = 0
    tool_latency_ms: float = 0.0
    observation_bytes: int = 0
    fatal_rate: float = 0.0
    turn_count: int = 0
    compare_target_kind: str = "base"
    base_model_id: str = ""
    adapter_manifest_path: str = ""
    adapter_set_hash: str = ""
    adapter_activation_mode: str = ""
    created_at_unix_ms: int = 0
    trajectory_provenance: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "model_id": self.model_id,
            "task_kind": self.task_kind,
            "source_repo": self.source_repo,
            "suite": self.suite,
            "context_length": self.context_length,
            "generation_length": self.generation_length,
            "batch_size": self.batch_size,
            "repeat_index": self.repeat_index,
            "request_index": self.request_index,
            "phase": self.phase,
            "phase_index": self.phase_index,
            "status": self.status,
            "error_code": self.error_code,
            "error_stage": self.error_stage,
            "duration_ms": self.duration_ms,
            "ttft_ms": self.ttft_ms,
            "request_latency_ms": self.request_latency_ms,
            "prefill_tokens_per_second": self.prefill_tokens_per_second,
            "decode_tokens_per_second": self.decode_tokens_per_second,
            "peak_memory_bytes": self.peak_memory_bytes,
            "dataset_materialize_ms": self.dataset_materialize_ms,
            "prompt_render_ms": self.prompt_render_ms,
            "warmup_ms": self.warmup_ms,
            "prefill_ms": self.prefill_ms,
            "decode_ms": self.decode_ms,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "first_token_index": self.first_token_index,
            "cache_hit": self.cache_hit,
            "runtime_kind": self.runtime_kind,
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "tool_arguments_json": self.tool_arguments_json,
            "tool_observation_json": self.tool_observation_json,
            "tool_call_count": self.tool_call_count,
            "tool_latency_ms": self.tool_latency_ms,
            "observation_bytes": self.observation_bytes,
            "fatal_rate": self.fatal_rate,
            "turn_count": self.turn_count,
            "compare_target_kind": self.compare_target_kind,
            "base_model_id": self.base_model_id,
            "adapter_manifest_path": self.adapter_manifest_path,
            "adapter_set_hash": self.adapter_set_hash,
            "adapter_activation_mode": self.adapter_activation_mode,
            "created_at_unix_ms": self.created_at_unix_ms,
        }
        append_trajectory_provenance(payload, self.trajectory_provenance)
        return payload


@dataclass(frozen=True)
class ServingBenchmarkResult:
    schema_version: str
    job_id: str
    suite: str
    metrics: tuple[BenchmarkMetricValue, ...]
    report_path: str
    report_markdown: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "suite": self.suite,
            "metrics": [metric.to_dict() for metric in self.metrics],
            "report_path": self.report_path,
            "report_markdown": self.report_markdown,
        }


@dataclass(frozen=True)
class BenchmarkMatrixJob:
    schema_version: str
    job_id: str
    model_id: str
    task_kind: str
    source_repo: str
    suite_ids: tuple[str, ...]
    benchmark_mode: str
    status: str
    output_dir: str
    created_at_unix_ms: int
    updated_at_unix_ms: int
    parameters: dict[str, str] = field(default_factory=dict)
    trajectory_provenance: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "model_id": self.model_id,
            "task_kind": self.task_kind,
            "source_repo": self.source_repo,
            "suite_ids": list(self.suite_ids),
            "benchmark_mode": self.benchmark_mode,
            "status": self.status,
            "output_dir": self.output_dir,
            "parameters": dict(self.parameters),
            "created_at_unix_ms": self.created_at_unix_ms,
            "updated_at_unix_ms": self.updated_at_unix_ms,
        }
        append_trajectory_provenance(payload, self.trajectory_provenance)
        return payload


@dataclass(frozen=True)
class BenchmarkMatrixSummaryRow:
    job_id: str
    task_kind: str
    source_repo: str
    model_id: str
    suite_id: str
    context_length: int
    generation_length: int
    batch_size: int
    cache_profile: str
    reasoning_mode: str
    structured_output_mode: str
    concurrency_level: int
    repeats: int
    requests: int
    duration_seconds: int
    ttft_mean_ms: float
    ttft_std_ms: float
    request_latency_mean_ms: float
    request_latency_std_ms: float
    prefill_tokens_per_second_mean: float
    decode_tokens_per_second_mean: float
    throughput_requests_per_second: float
    throughput_tokens_per_second: float
    success_rate: float
    peak_memory_bytes_max: int
    queue_wait_mean_ms: float
    queue_wait_p95_ms: float
    cell_wall_ms: float = 0.0
    completed_count: int = 0
    failed_count: int = 0
    ttft_p50_ms: float = 0.0
    ttft_p95_ms: float = 0.0
    request_latency_p50_ms: float = 0.0
    request_latency_p95_ms: float = 0.0
    tool_call_count: int = 0
    tool_latency_ms: float = 0.0
    observation_bytes: int = 0
    fatal_rate: float = 0.0
    turn_count: int = 0
    created_at_unix_ms: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "task_kind": self.task_kind,
            "source_repo": self.source_repo,
            "model_id": self.model_id,
            "suite_id": self.suite_id,
            "context_length": self.context_length,
            "generation_length": self.generation_length,
            "batch_size": self.batch_size,
            "cache_profile": self.cache_profile,
            "reasoning_mode": self.reasoning_mode,
            "structured_output_mode": self.structured_output_mode,
            "concurrency_level": self.concurrency_level,
            "repeats": self.repeats,
            "requests": self.requests,
            "duration_seconds": self.duration_seconds,
            "ttft_mean_ms": self.ttft_mean_ms,
            "ttft_std_ms": self.ttft_std_ms,
            "request_latency_mean_ms": self.request_latency_mean_ms,
            "request_latency_std_ms": self.request_latency_std_ms,
            "prefill_tokens_per_second_mean": self.prefill_tokens_per_second_mean,
            "decode_tokens_per_second_mean": self.decode_tokens_per_second_mean,
            "throughput_requests_per_second": self.throughput_requests_per_second,
            "throughput_tokens_per_second": self.throughput_tokens_per_second,
            "success_rate": self.success_rate,
            "peak_memory_bytes_max": self.peak_memory_bytes_max,
            "queue_wait_mean_ms": self.queue_wait_mean_ms,
            "queue_wait_p95_ms": self.queue_wait_p95_ms,
            "cell_wall_ms": self.cell_wall_ms,
            "completed_count": self.completed_count,
            "failed_count": self.failed_count,
            "ttft_p50_ms": self.ttft_p50_ms,
            "ttft_p95_ms": self.ttft_p95_ms,
            "request_latency_p50_ms": self.request_latency_p50_ms,
            "request_latency_p95_ms": self.request_latency_p95_ms,
            "tool_call_count": self.tool_call_count,
            "tool_latency_ms": self.tool_latency_ms,
            "observation_bytes": self.observation_bytes,
            "fatal_rate": self.fatal_rate,
            "turn_count": self.turn_count,
            "created_at_unix_ms": self.created_at_unix_ms,
        }


@dataclass(frozen=True)
class BenchmarkMatrixRequestRow:
    job_id: str
    cell_id: str
    task_kind: str
    suite_id: str
    context_length: int
    generation_length: int
    batch_size: int
    cache_profile: str
    reasoning_mode: str
    structured_output_mode: str
    concurrency_level: int
    repeat_index: int
    request_index: int
    ttft_ms: float
    request_latency_ms: float
    prefill_tokens_per_second: float
    decode_tokens_per_second: float
    queue_wait_ms: float
    peak_memory_bytes: int
    status: str
    error_code: str
    created_at_unix_ms: int
    dataset_materialize_ms: float = 0.0
    prompt_render_ms: float = 0.0
    warmup_ms: float = 0.0
    prefill_ms: float = 0.0
    decode_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    first_token_index: int = 0
    cache_hit: bool = False
    runtime_kind: str = ""
    error_stage: str = ""
    speculative_acceptance_rate: float = 0.0
    speculative_rollback_rate: float = 0.0
    speculative_accepted_tokens: int = 0
    speculative_rejected_tokens: int = 0
    speculative_fallback_count: int = 0
    speculative_num_draft_tokens: int = 0
    speculative_draft_model_configured: bool = False
    speculative_draft_propose_ms: float = 0.0
    speculative_target_verify_ms: float = 0.0
    dflash_enabled: bool = False
    dflash_block_size: int = 0
    dflash_rollback_count: int = 0
    dflash_target_hidden_layers: int = 0
    tool_call_count: int = 0
    tool_latency_ms: float = 0.0
    observation_bytes: int = 0
    fatal_rate: float = 0.0
    turn_count: int = 0
    agentic_tool_registry: dict[str, object] | None = None
    agentic_tool_calls: tuple[dict[str, object], ...] = ()
    agentic_tool_observations: tuple[dict[str, object], ...] = ()
    agentic_tool_metrics: dict[str, float] | None = None
    trajectory_provenance: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "job_id": self.job_id,
            "cell_id": self.cell_id,
            "task_kind": self.task_kind,
            "suite_id": self.suite_id,
            "context_length": self.context_length,
            "generation_length": self.generation_length,
            "batch_size": self.batch_size,
            "cache_profile": self.cache_profile,
            "reasoning_mode": self.reasoning_mode,
            "structured_output_mode": self.structured_output_mode,
            "concurrency_level": self.concurrency_level,
            "repeat_index": self.repeat_index,
            "request_index": self.request_index,
            "ttft_ms": self.ttft_ms,
            "request_latency_ms": self.request_latency_ms,
            "prefill_tokens_per_second": self.prefill_tokens_per_second,
            "decode_tokens_per_second": self.decode_tokens_per_second,
            "queue_wait_ms": self.queue_wait_ms,
            "peak_memory_bytes": self.peak_memory_bytes,
            "status": self.status,
            "error_code": self.error_code,
            "dataset_materialize_ms": self.dataset_materialize_ms,
            "prompt_render_ms": self.prompt_render_ms,
            "warmup_ms": self.warmup_ms,
            "prefill_ms": self.prefill_ms,
            "decode_ms": self.decode_ms,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "first_token_index": self.first_token_index,
            "cache_hit": self.cache_hit,
            "runtime_kind": self.runtime_kind,
            "error_stage": self.error_stage,
            "speculative_acceptance_rate": self.speculative_acceptance_rate,
            "speculative_rollback_rate": self.speculative_rollback_rate,
            "speculative_accepted_tokens": self.speculative_accepted_tokens,
            "speculative_rejected_tokens": self.speculative_rejected_tokens,
            "speculative_fallback_count": self.speculative_fallback_count,
            "speculative_num_draft_tokens": self.speculative_num_draft_tokens,
            "speculative_draft_model_configured": self.speculative_draft_model_configured,
            "speculative_draft_propose_ms": self.speculative_draft_propose_ms,
            "speculative_target_verify_ms": self.speculative_target_verify_ms,
            "dflash_enabled": self.dflash_enabled,
            "dflash_block_size": self.dflash_block_size,
            "dflash_rollback_count": self.dflash_rollback_count,
            "dflash_target_hidden_layers": self.dflash_target_hidden_layers,
            "tool_call_count": self.tool_call_count,
            "tool_latency_ms": self.tool_latency_ms,
            "observation_bytes": self.observation_bytes,
            "fatal_rate": self.fatal_rate,
            "turn_count": self.turn_count,
            "created_at_unix_ms": self.created_at_unix_ms,
        }
        _append_agentic_tool_evidence(
            payload,
            registry=self.agentic_tool_registry,
            calls=self.agentic_tool_calls,
            observations=self.agentic_tool_observations,
            metrics=self.agentic_tool_metrics,
        )
        append_trajectory_provenance(payload, self.trajectory_provenance)
        return payload


def build_serving_benchmark_job(
    *,
    job_id: str,
    model_id: str,
    task_kind: str = "text-generation",
    source_repo: str = "",
    suites: tuple[str, ...],
    context_lengths: tuple[int, ...] = (),
    generation_length: int = 0,
    batch_sizes: tuple[int, ...] = (),
    repeats: int = 1,
    cache_profile: str = "",
    reasoning_mode: str = "",
    structured_output_mode: str = "",
    request_p50_ms: float = 0.0,
    request_p95_ms: float = 0.0,
    parameters: dict[str, str],
    status: str,
    output_dir: str,
    created_at_unix_ms: int = 0,
    updated_at_unix_ms: int = 0,
    suite_metadata: dict[str, dict[str, object]] | None = None,
    trajectory_provenance: dict[str, object] | None = None,
) -> ServingBenchmarkJob:
    return ServingBenchmarkJob(
        schema_version=_SERVING_BENCHMARK_JOB_SCHEMA_VERSION,
        job_id=job_id,
        model_id=model_id,
        task_kind=task_kind,
        source_repo=source_repo,
        suites=suites,
        context_lengths=context_lengths,
        generation_length=generation_length,
        batch_sizes=batch_sizes,
        repeats=repeats,
        cache_profile=cache_profile,
        reasoning_mode=reasoning_mode,
        structured_output_mode=structured_output_mode,
        request_p50_ms=request_p50_ms,
        request_p95_ms=request_p95_ms,
        parameters=dict(parameters),
        status=status,
        output_dir=output_dir,
        created_at_unix_ms=created_at_unix_ms,
        updated_at_unix_ms=updated_at_unix_ms,
        suite_metadata=dict(suite_metadata or {}),
        trajectory_provenance=dict(trajectory_provenance or {}),
    )


def _append_agentic_tool_evidence(
    payload: dict[str, object],
    *,
    registry: dict[str, object] | None,
    calls: tuple[dict[str, object], ...],
    observations: tuple[dict[str, object], ...],
    metrics: dict[str, float] | None,
) -> None:
    if registry:
        payload["agentic_tool_registry"] = dict(registry)
    if calls:
        payload["agentic_tool_calls"] = [dict(call) for call in calls]
    if observations:
        payload["agentic_tool_observations"] = [dict(observation) for observation in observations]
    if metrics:
        payload["agentic_tool_metrics"] = dict(metrics)


def _compact_json_text(payload: object) -> str:
    if not isinstance(payload, dict) or not payload:
        return ""
    return json.dumps(payload, **_COMPACT_JSON_KWARGS)


def _agentic_metric_float(metrics: dict[str, float] | None, key: str) -> float:
    if not metrics:
        return 0.0
    try:
        return float(metrics.get(key, 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _agentic_metric_int(metrics: dict[str, float] | None, key: str) -> int:
    return int(_agentic_metric_float(metrics, key))


def _derived_agentic_benchmark_fields(
    *,
    metrics: dict[str, float] | None,
    tool_call_count: int,
    tool_latency_ms: float,
    observation_bytes: int,
    fatal_rate: float,
    turn_count: int,
) -> dict[str, object]:
    if not metrics:
        return {
            "tool_call_count": tool_call_count,
            "tool_latency_ms": tool_latency_ms,
            "observation_bytes": observation_bytes,
            "fatal_rate": fatal_rate,
            "turn_count": turn_count,
        }
    derived_tool_call_count = _agentic_metric_int(metrics, _AGENTIC_TOOL_CALL_COUNT_KEY)
    derived_observation_count = _agentic_metric_int(metrics, _AGENTIC_TOOL_OBSERVATION_COUNT_KEY)
    timeout_count = _agentic_metric_float(metrics, _AGENTIC_TOOL_TIMEOUT_COUNT_KEY)
    failed_count = _agentic_metric_float(metrics, _AGENTIC_TOOL_FAILED_COUNT_KEY)
    return {
        "tool_call_count": tool_call_count or derived_tool_call_count,
        "tool_latency_ms": tool_latency_ms
        or _agentic_metric_float(metrics, _AGENTIC_TOOL_LATENCY_MS_KEY),
        "observation_bytes": observation_bytes
        or _agentic_metric_int(metrics, _AGENTIC_TOOL_OBSERVATION_BYTES_KEY),
        "fatal_rate": fatal_rate or (1.0 if timeout_count + failed_count > 0.0 else 0.0),
        "turn_count": turn_count or (derived_tool_call_count + derived_observation_count),
    }


def benchmark_matrix_tool_turn_summary_fields(
    rows: tuple["BenchmarkMatrixRequestRow", ...],
) -> dict[str, object]:
    fatal_count = sum(1 for row in rows if row.fatal_rate > 0.0)
    return {
        "tool_call_count": sum(row.tool_call_count for row in rows),
        "tool_latency_ms": round(sum(row.tool_latency_ms for row in rows), 6),
        "observation_bytes": sum(row.observation_bytes for row in rows),
        "fatal_rate": round(fatal_count / max(len(rows), 1), 6),
        "turn_count": sum(row.turn_count for row in rows),
    }


def build_serving_benchmark_request_row(
    *,
    job_id: str,
    model_id: str,
    task_kind: str,
    source_repo: str,
    suite: str,
    context_length: int,
    generation_length: int,
    batch_size: int,
    repeat_index: int,
    request_index: int,
    phase: str,
    phase_index: int,
    status: str,
    error_code: str = "",
    error_stage: str = "",
    duration_ms: float = 0.0,
    ttft_ms: float = 0.0,
    request_latency_ms: float = 0.0,
    prefill_tokens_per_second: float = 0.0,
    decode_tokens_per_second: float = 0.0,
    peak_memory_bytes: float = 0.0,
    dataset_materialize_ms: float = 0.0,
    prompt_render_ms: float = 0.0,
    warmup_ms: float = 0.0,
    prefill_ms: float = 0.0,
    decode_ms: float = 0.0,
    tokens_in: int = 0,
    tokens_out: int = 0,
    first_token_index: int = 0,
    cache_hit: bool = False,
    runtime_kind: str = "",
    tool_call_id: str = "",
    tool_name: str = "",
    tool_arguments: dict[str, object] | None = None,
    tool_observation: dict[str, object] | None = None,
    tool_call_count: int = 0,
    tool_latency_ms: float = 0.0,
    observation_bytes: int = 0,
    fatal_rate: float = 0.0,
    turn_count: int = 0,
    compare_target_kind: str = "base",
    base_model_id: str = "",
    adapter_manifest_path: str = "",
    adapter_set_hash: str = "",
    adapter_activation_mode: str = "",
    agentic_tool_metrics: dict[str, float] | None = None,
    created_at_unix_ms: int = 0,
    trajectory_provenance: dict[str, object] | None = None,
) -> ServingBenchmarkRequestRow:
    agentic_fields = _derived_agentic_benchmark_fields(
        metrics=agentic_tool_metrics,
        tool_call_count=tool_call_count,
        tool_latency_ms=tool_latency_ms,
        observation_bytes=observation_bytes,
        fatal_rate=fatal_rate,
        turn_count=turn_count,
    )
    resolved_compare_target_kind = (
        compare_target_kind
        or ("adapter" if adapter_manifest_path or adapter_set_hash else "base")
    )
    resolved_base_model_id = (
        base_model_id
        or (model_id if resolved_compare_target_kind == "base" else "")
    )
    return ServingBenchmarkRequestRow(
        schema_version=_SERVING_BENCHMARK_REQUEST_ROW_SCHEMA_VERSION,
        job_id=job_id,
        model_id=model_id,
        task_kind=task_kind,
        source_repo=source_repo,
        suite=suite,
        context_length=context_length,
        generation_length=generation_length,
        batch_size=batch_size,
        repeat_index=repeat_index,
        request_index=request_index,
        phase=phase,
        phase_index=phase_index,
        status=status,
        error_code=error_code,
        error_stage=error_stage,
        duration_ms=duration_ms,
        ttft_ms=ttft_ms,
        request_latency_ms=request_latency_ms,
        prefill_tokens_per_second=prefill_tokens_per_second,
        decode_tokens_per_second=decode_tokens_per_second,
        peak_memory_bytes=peak_memory_bytes,
        dataset_materialize_ms=dataset_materialize_ms,
        prompt_render_ms=prompt_render_ms,
        warmup_ms=warmup_ms,
        prefill_ms=prefill_ms,
        decode_ms=decode_ms,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        first_token_index=first_token_index,
        cache_hit=cache_hit,
        runtime_kind=runtime_kind,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        tool_arguments_json=_compact_json_text(tool_arguments or {}),
        tool_observation_json=_compact_json_text(tool_observation or {}),
        tool_call_count=int(agentic_fields["tool_call_count"]),
        tool_latency_ms=float(agentic_fields["tool_latency_ms"]),
        observation_bytes=int(agentic_fields["observation_bytes"]),
        fatal_rate=float(agentic_fields["fatal_rate"]),
        turn_count=int(agentic_fields["turn_count"]),
        compare_target_kind=resolved_compare_target_kind,
        base_model_id=resolved_base_model_id,
        adapter_manifest_path=adapter_manifest_path,
        adapter_set_hash=adapter_set_hash,
        adapter_activation_mode=adapter_activation_mode,
        created_at_unix_ms=created_at_unix_ms,
        trajectory_provenance=dict(trajectory_provenance or {}),
    )


def build_benchmark_matrix_job(
    *,
    job_id: str,
    model_id: str,
    task_kind: str,
    source_repo: str,
    suite_ids: tuple[str, ...],
    status: str,
    output_dir: str,
    created_at_unix_ms: int = 0,
    updated_at_unix_ms: int = 0,
    parameters: dict[str, str] | None = None,
    trajectory_provenance: dict[str, object] | None = None,
) -> BenchmarkMatrixJob:
    return BenchmarkMatrixJob(
        schema_version=_BENCHMARK_MATRIX_JOB_SCHEMA_VERSION,
        job_id=job_id,
        model_id=model_id,
        task_kind=task_kind,
        source_repo=source_repo,
        suite_ids=suite_ids,
        benchmark_mode="matrix",
        status=status,
        output_dir=output_dir,
        created_at_unix_ms=created_at_unix_ms,
        updated_at_unix_ms=updated_at_unix_ms,
        parameters=dict(parameters or {}),
        trajectory_provenance=dict(trajectory_provenance or {}),
    )


def build_benchmark_matrix_summary_row(
    *,
    job_id: str,
    task_kind: str,
    source_repo: str,
    model_id: str,
    suite_id: str,
    context_length: int,
    generation_length: int,
    batch_size: int,
    cache_profile: str,
    reasoning_mode: str,
    structured_output_mode: str,
    concurrency_level: int,
    repeats: int,
    requests: int,
    duration_seconds: int,
    ttft_mean_ms: float,
    ttft_std_ms: float,
    request_latency_mean_ms: float,
    request_latency_std_ms: float,
    prefill_tokens_per_second_mean: float,
    decode_tokens_per_second_mean: float,
    throughput_requests_per_second: float,
    throughput_tokens_per_second: float,
    success_rate: float,
    peak_memory_bytes_max: int,
    queue_wait_mean_ms: float,
    queue_wait_p95_ms: float,
    cell_wall_ms: float = 0.0,
    completed_count: int = 0,
    failed_count: int = 0,
    ttft_p50_ms: float = 0.0,
    ttft_p95_ms: float = 0.0,
    request_latency_p50_ms: float = 0.0,
    request_latency_p95_ms: float = 0.0,
    tool_call_count: int = 0,
    tool_latency_ms: float = 0.0,
    observation_bytes: int = 0,
    fatal_rate: float = 0.0,
    turn_count: int = 0,
    created_at_unix_ms: int = 0,
) -> BenchmarkMatrixSummaryRow:
    return BenchmarkMatrixSummaryRow(
        job_id=job_id,
        task_kind=task_kind,
        source_repo=source_repo,
        model_id=model_id,
        suite_id=suite_id,
        context_length=context_length,
        generation_length=generation_length,
        batch_size=batch_size,
        cache_profile=cache_profile,
        reasoning_mode=reasoning_mode,
        structured_output_mode=structured_output_mode,
        concurrency_level=concurrency_level,
        repeats=repeats,
        requests=requests,
        duration_seconds=duration_seconds,
        ttft_mean_ms=ttft_mean_ms,
        ttft_std_ms=ttft_std_ms,
        request_latency_mean_ms=request_latency_mean_ms,
        request_latency_std_ms=request_latency_std_ms,
        prefill_tokens_per_second_mean=prefill_tokens_per_second_mean,
        decode_tokens_per_second_mean=decode_tokens_per_second_mean,
        throughput_requests_per_second=throughput_requests_per_second,
        throughput_tokens_per_second=throughput_tokens_per_second,
        success_rate=success_rate,
        peak_memory_bytes_max=peak_memory_bytes_max,
        queue_wait_mean_ms=queue_wait_mean_ms,
        queue_wait_p95_ms=queue_wait_p95_ms,
        cell_wall_ms=cell_wall_ms,
        completed_count=completed_count,
        failed_count=failed_count,
        ttft_p50_ms=ttft_p50_ms,
        ttft_p95_ms=ttft_p95_ms,
        request_latency_p50_ms=request_latency_p50_ms,
        request_latency_p95_ms=request_latency_p95_ms,
        tool_call_count=tool_call_count,
        tool_latency_ms=tool_latency_ms,
        observation_bytes=observation_bytes,
        fatal_rate=fatal_rate,
        turn_count=turn_count,
        created_at_unix_ms=created_at_unix_ms,
    )


def build_benchmark_matrix_request_row(
    *,
    job_id: str,
    cell_id: str,
    task_kind: str,
    suite_id: str,
    context_length: int,
    generation_length: int,
    batch_size: int,
    cache_profile: str,
    reasoning_mode: str,
    structured_output_mode: str,
    concurrency_level: int,
    repeat_index: int,
    request_index: int,
    ttft_ms: float,
    request_latency_ms: float,
    prefill_tokens_per_second: float,
    decode_tokens_per_second: float,
    queue_wait_ms: float,
    peak_memory_bytes: int,
    status: str,
    error_code: str,
    created_at_unix_ms: int,
    dataset_materialize_ms: float = 0.0,
    prompt_render_ms: float = 0.0,
    warmup_ms: float = 0.0,
    prefill_ms: float = 0.0,
    decode_ms: float = 0.0,
    tokens_in: int = 0,
    tokens_out: int = 0,
    first_token_index: int = 0,
    cache_hit: bool = False,
    runtime_kind: str = "",
    error_stage: str = "",
    speculative_acceptance_rate: float = 0.0,
    speculative_rollback_rate: float = 0.0,
    speculative_accepted_tokens: int = 0,
    speculative_rejected_tokens: int = 0,
    speculative_fallback_count: int = 0,
    speculative_num_draft_tokens: int = 0,
    speculative_draft_model_configured: bool = False,
    speculative_draft_propose_ms: float = 0.0,
    speculative_target_verify_ms: float = 0.0,
    dflash_enabled: bool = False,
    dflash_block_size: int = 0,
    dflash_rollback_count: int = 0,
    dflash_target_hidden_layers: int = 0,
    tool_call_count: int = 0,
    tool_latency_ms: float = 0.0,
    observation_bytes: int = 0,
    fatal_rate: float = 0.0,
    turn_count: int = 0,
    agentic_tool_registry: dict[str, object] | None = None,
    agentic_tool_calls: tuple[dict[str, object], ...] = (),
    agentic_tool_observations: tuple[dict[str, object], ...] = (),
    agentic_tool_metrics: dict[str, float] | None = None,
    trajectory_provenance: dict[str, object] | None = None,
) -> BenchmarkMatrixRequestRow:
    agentic_fields = _derived_agentic_benchmark_fields(
        metrics=agentic_tool_metrics,
        tool_call_count=tool_call_count,
        tool_latency_ms=tool_latency_ms,
        observation_bytes=observation_bytes,
        fatal_rate=fatal_rate,
        turn_count=turn_count,
    )
    return BenchmarkMatrixRequestRow(
        job_id=job_id,
        cell_id=cell_id,
        task_kind=task_kind,
        suite_id=suite_id,
        context_length=context_length,
        generation_length=generation_length,
        batch_size=batch_size,
        cache_profile=cache_profile,
        reasoning_mode=reasoning_mode,
        structured_output_mode=structured_output_mode,
        concurrency_level=concurrency_level,
        repeat_index=repeat_index,
        request_index=request_index,
        ttft_ms=ttft_ms,
        request_latency_ms=request_latency_ms,
        prefill_tokens_per_second=prefill_tokens_per_second,
        decode_tokens_per_second=decode_tokens_per_second,
        queue_wait_ms=queue_wait_ms,
        peak_memory_bytes=peak_memory_bytes,
        status=status,
        error_code=error_code,
        created_at_unix_ms=created_at_unix_ms,
        dataset_materialize_ms=dataset_materialize_ms,
        prompt_render_ms=prompt_render_ms,
        warmup_ms=warmup_ms,
        prefill_ms=prefill_ms,
        decode_ms=decode_ms,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        first_token_index=first_token_index,
        cache_hit=cache_hit,
        runtime_kind=runtime_kind,
        error_stage=error_stage,
        speculative_acceptance_rate=speculative_acceptance_rate,
        speculative_rollback_rate=speculative_rollback_rate,
        speculative_accepted_tokens=speculative_accepted_tokens,
        speculative_rejected_tokens=speculative_rejected_tokens,
        speculative_fallback_count=speculative_fallback_count,
        speculative_num_draft_tokens=speculative_num_draft_tokens,
        speculative_draft_model_configured=speculative_draft_model_configured,
        speculative_draft_propose_ms=speculative_draft_propose_ms,
        speculative_target_verify_ms=speculative_target_verify_ms,
        dflash_enabled=dflash_enabled,
        dflash_block_size=dflash_block_size,
        dflash_rollback_count=dflash_rollback_count,
        dflash_target_hidden_layers=dflash_target_hidden_layers,
        tool_call_count=int(agentic_fields["tool_call_count"]),
        tool_latency_ms=float(agentic_fields["tool_latency_ms"]),
        observation_bytes=int(agentic_fields["observation_bytes"]),
        fatal_rate=float(agentic_fields["fatal_rate"]),
        turn_count=int(agentic_fields["turn_count"]),
        agentic_tool_registry=dict(agentic_tool_registry or {}),
        agentic_tool_calls=tuple(dict(call) for call in agentic_tool_calls),
        agentic_tool_observations=tuple(dict(observation) for observation in agentic_tool_observations),
        agentic_tool_metrics=dict(agentic_tool_metrics or {}),
        trajectory_provenance=dict(trajectory_provenance or {}),
    )


def build_serving_benchmark_context_row(
    *,
    job_id: str,
    model_id: str,
    task_kind: str,
    source_repo: str,
    suite: str,
    context_length: int,
    generation_length: int,
    batch_size: int,
    repeat_index: int,
    prefill_tokens_per_second: float,
    decode_tokens_per_second: float,
    ttft_ms: float,
    request_latency_ms: float,
    peak_memory_bytes: float,
    speedup_vs_batch_1: float,
    cache_profile: str,
    reasoning_mode: str,
    structured_output_mode: str,
    dataset_materialize_ms: float = 0.0,
    prompt_render_ms: float = 0.0,
    warmup_ms: float = 0.0,
    prefill_ms: float = 0.0,
    decode_ms: float = 0.0,
    tokens_in: int = 0,
    tokens_out: int = 0,
    first_token_index: int = 0,
    cache_hit: bool = False,
    runtime_kind: str = "",
    error_stage: str = "",
    speculative_acceptance_rate: float = 0.0,
    speculative_rollback_rate: float = 0.0,
    speculative_accepted_tokens: int = 0,
    speculative_rejected_tokens: int = 0,
    speculative_fallback_count: int = 0,
    speculative_num_draft_tokens: int = 0,
    speculative_draft_model_configured: bool = False,
    speculative_draft_propose_ms: float = 0.0,
    speculative_target_verify_ms: float = 0.0,
    dflash_enabled: bool = False,
    dflash_block_size: int = 0,
    dflash_rollback_count: int = 0,
    dflash_target_hidden_layers: int = 0,
    tool_call_count: int = 0,
    tool_latency_ms: float = 0.0,
    observation_bytes: int = 0,
    fatal_rate: float = 0.0,
    turn_count: int = 0,
    agentic_tool_registry: dict[str, object] | None = None,
    agentic_tool_calls: tuple[dict[str, object], ...] = (),
    agentic_tool_observations: tuple[dict[str, object], ...] = (),
    agentic_tool_metrics: dict[str, float] | None = None,
    trajectory_provenance: dict[str, object] | None = None,
) -> ServingBenchmarkContextRow:
    agentic_fields = _derived_agentic_benchmark_fields(
        metrics=agentic_tool_metrics,
        tool_call_count=tool_call_count,
        tool_latency_ms=tool_latency_ms,
        observation_bytes=observation_bytes,
        fatal_rate=fatal_rate,
        turn_count=turn_count,
    )
    return ServingBenchmarkContextRow(
        schema_version="melix.serving_benchmark_context_row.v1",
        job_id=job_id,
        model_id=model_id,
        task_kind=task_kind,
        source_repo=source_repo,
        suite=suite,
        context_length=context_length,
        generation_length=generation_length,
        batch_size=batch_size,
        repeat_index=repeat_index,
        prefill_tokens_per_second=prefill_tokens_per_second,
        decode_tokens_per_second=decode_tokens_per_second,
        ttft_ms=ttft_ms,
        request_latency_ms=request_latency_ms,
        peak_memory_bytes=peak_memory_bytes,
        speedup_vs_batch_1=speedup_vs_batch_1,
        cache_profile=cache_profile,
        reasoning_mode=reasoning_mode,
        structured_output_mode=structured_output_mode,
        dataset_materialize_ms=dataset_materialize_ms,
        prompt_render_ms=prompt_render_ms,
        warmup_ms=warmup_ms,
        prefill_ms=prefill_ms,
        decode_ms=decode_ms,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        first_token_index=first_token_index,
        cache_hit=cache_hit,
        runtime_kind=runtime_kind,
        error_stage=error_stage,
        speculative_acceptance_rate=speculative_acceptance_rate,
        speculative_rollback_rate=speculative_rollback_rate,
        speculative_accepted_tokens=speculative_accepted_tokens,
        speculative_rejected_tokens=speculative_rejected_tokens,
        speculative_fallback_count=speculative_fallback_count,
        speculative_num_draft_tokens=speculative_num_draft_tokens,
        speculative_draft_model_configured=speculative_draft_model_configured,
        speculative_draft_propose_ms=speculative_draft_propose_ms,
        speculative_target_verify_ms=speculative_target_verify_ms,
        dflash_enabled=dflash_enabled,
        dflash_block_size=dflash_block_size,
        dflash_rollback_count=dflash_rollback_count,
        dflash_target_hidden_layers=dflash_target_hidden_layers,
        tool_call_count=int(agentic_fields["tool_call_count"]),
        tool_latency_ms=float(agentic_fields["tool_latency_ms"]),
        observation_bytes=int(agentic_fields["observation_bytes"]),
        fatal_rate=float(agentic_fields["fatal_rate"]),
        turn_count=int(agentic_fields["turn_count"]),
        agentic_tool_registry=dict(agentic_tool_registry or {}),
        agentic_tool_calls=tuple(dict(call) for call in agentic_tool_calls),
        agentic_tool_observations=tuple(dict(observation) for observation in agentic_tool_observations),
        agentic_tool_metrics=dict(agentic_tool_metrics or {}),
        trajectory_provenance=dict(trajectory_provenance or {}),
    )


def build_serving_benchmark_batch_row(
    *,
    job_id: str,
    model_id: str,
    task_kind: str,
    source_repo: str,
    suite: str,
    context_length: int,
    generation_length: int,
    batch_size: int,
    repeat_index: int,
    prefill_tokens_per_second: float,
    decode_tokens_per_second: float,
    ttft_ms: float,
    request_latency_ms: float,
    peak_memory_bytes: float,
    speedup_vs_batch_1: float,
    cache_profile: str,
    reasoning_mode: str,
    structured_output_mode: str,
    dataset_materialize_ms: float = 0.0,
    prompt_render_ms: float = 0.0,
    warmup_ms: float = 0.0,
    prefill_ms: float = 0.0,
    decode_ms: float = 0.0,
    tokens_in: int = 0,
    tokens_out: int = 0,
    first_token_index: int = 0,
    cache_hit: bool = False,
    runtime_kind: str = "",
    error_stage: str = "",
    speculative_acceptance_rate: float = 0.0,
    speculative_rollback_rate: float = 0.0,
    speculative_accepted_tokens: int = 0,
    speculative_rejected_tokens: int = 0,
    speculative_fallback_count: int = 0,
    speculative_num_draft_tokens: int = 0,
    speculative_draft_model_configured: bool = False,
    speculative_draft_propose_ms: float = 0.0,
    speculative_target_verify_ms: float = 0.0,
    dflash_enabled: bool = False,
    dflash_block_size: int = 0,
    dflash_rollback_count: int = 0,
    dflash_target_hidden_layers: int = 0,
    tool_call_count: int = 0,
    tool_latency_ms: float = 0.0,
    observation_bytes: int = 0,
    fatal_rate: float = 0.0,
    turn_count: int = 0,
    agentic_tool_registry: dict[str, object] | None = None,
    agentic_tool_calls: tuple[dict[str, object], ...] = (),
    agentic_tool_observations: tuple[dict[str, object], ...] = (),
    agentic_tool_metrics: dict[str, float] | None = None,
    trajectory_provenance: dict[str, object] | None = None,
) -> ServingBenchmarkBatchRow:
    agentic_fields = _derived_agentic_benchmark_fields(
        metrics=agentic_tool_metrics,
        tool_call_count=tool_call_count,
        tool_latency_ms=tool_latency_ms,
        observation_bytes=observation_bytes,
        fatal_rate=fatal_rate,
        turn_count=turn_count,
    )
    return ServingBenchmarkBatchRow(
        schema_version="melix.serving_benchmark_batch_row.v1",
        job_id=job_id,
        model_id=model_id,
        task_kind=task_kind,
        source_repo=source_repo,
        suite=suite,
        context_length=context_length,
        generation_length=generation_length,
        batch_size=batch_size,
        repeat_index=repeat_index,
        prefill_tokens_per_second=prefill_tokens_per_second,
        decode_tokens_per_second=decode_tokens_per_second,
        ttft_ms=ttft_ms,
        request_latency_ms=request_latency_ms,
        peak_memory_bytes=peak_memory_bytes,
        speedup_vs_batch_1=speedup_vs_batch_1,
        cache_profile=cache_profile,
        reasoning_mode=reasoning_mode,
        structured_output_mode=structured_output_mode,
        dataset_materialize_ms=dataset_materialize_ms,
        prompt_render_ms=prompt_render_ms,
        warmup_ms=warmup_ms,
        prefill_ms=prefill_ms,
        decode_ms=decode_ms,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        first_token_index=first_token_index,
        cache_hit=cache_hit,
        runtime_kind=runtime_kind,
        error_stage=error_stage,
        speculative_acceptance_rate=speculative_acceptance_rate,
        speculative_rollback_rate=speculative_rollback_rate,
        speculative_accepted_tokens=speculative_accepted_tokens,
        speculative_rejected_tokens=speculative_rejected_tokens,
        speculative_fallback_count=speculative_fallback_count,
        speculative_num_draft_tokens=speculative_num_draft_tokens,
        speculative_draft_model_configured=speculative_draft_model_configured,
        speculative_draft_propose_ms=speculative_draft_propose_ms,
        speculative_target_verify_ms=speculative_target_verify_ms,
        dflash_enabled=dflash_enabled,
        dflash_block_size=dflash_block_size,
        dflash_rollback_count=dflash_rollback_count,
        dflash_target_hidden_layers=dflash_target_hidden_layers,
        tool_call_count=int(agentic_fields["tool_call_count"]),
        tool_latency_ms=float(agentic_fields["tool_latency_ms"]),
        observation_bytes=int(agentic_fields["observation_bytes"]),
        fatal_rate=float(agentic_fields["fatal_rate"]),
        turn_count=int(agentic_fields["turn_count"]),
        agentic_tool_registry=dict(agentic_tool_registry or {}),
        agentic_tool_calls=tuple(dict(call) for call in agentic_tool_calls),
        agentic_tool_observations=tuple(dict(observation) for observation in agentic_tool_observations),
        agentic_tool_metrics=dict(agentic_tool_metrics or {}),
        trajectory_provenance=dict(trajectory_provenance or {}),
    )


def build_serving_benchmark_results(
    *,
    job_id: str,
    metrics: dict[str, float],
    units: dict[str, str],
    report_path: str,
    report_markdown: str,
) -> tuple[ServingBenchmarkResult, ...]:
    grouped: dict[str, list[BenchmarkMetricValue]] = defaultdict(list)
    for name in sorted(metrics):
        grouped[_benchmark_suite_for_metric(name)].append(
            BenchmarkMetricValue(name=name, value=float(metrics[name]), unit=units.get(name, ""))
        )

    return tuple(
        ServingBenchmarkResult(
            schema_version=_SERVING_BENCHMARK_RESULT_SCHEMA_VERSION,
            job_id=job_id,
            suite=suite,
            metrics=tuple(entries),
            report_path=report_path,
            report_markdown=report_markdown,
        )
        for suite, entries in sorted(grouped.items())
    )


def build_evaluation_job(
    *,
    job_id: str,
    model_id: str,
    task_kind: str = "text-generation",
    source_repo: str = "",
    suite_id: str,
    dataset_id: str,
    sample_size: int,
    scoring_mode: str,
    parameters: dict[str, str],
    status: str,
    output_dir: str = "",
    created_at_unix_ms: int = 0,
    updated_at_unix_ms: int = 0,
    trajectory_provenance: dict[str, object] | None = None,
) -> EvaluationJob:
    return build_evaluation_job_record(
        job_id=job_id,
        model_id=model_id,
        task_kind=task_kind,
        source_repo=source_repo,
        suite_id=suite_id,
        dataset_id=dataset_id,
        sample_size=sample_size,
        scoring_mode=scoring_mode,
        parameters=parameters,
        status=status,
        output_dir=output_dir,
        created_at_unix_ms=created_at_unix_ms,
        updated_at_unix_ms=updated_at_unix_ms,
        trajectory_provenance=trajectory_provenance,
    )


def build_evaluation_result(
    *,
    job_id: str,
    suite_id: str,
    dataset_id: str,
    sample_size: int,
    metrics: dict[str, float],
    report_path: str,
    units: dict[str, str] | None = None,
) -> EvaluationResult:
    return build_evaluation_result_record(
        job_id=job_id,
        suite_id=suite_id,
        dataset_id=dataset_id,
        sample_size=sample_size,
        metrics=metrics,
        report_path=report_path,
        units=units,
    )


def build_evaluation_sample(
    *,
    job_id: str,
    suite_id: str,
    dataset_id: str,
    sample_id: str,
    question: str,
    expected: str,
    predicted: str,
    raw_response: str,
    correct: bool,
    time_s: float,
    parse_status: str,
    trajectory_provenance: dict[str, object] | None = None,
) -> EvaluationSample:
    return build_evaluation_sample_record(
        job_id=job_id,
        suite_id=suite_id,
        dataset_id=dataset_id,
        sample_id=sample_id,
        system="",
        input_text=question,
        target=expected,
        raw_response=raw_response,
        extracted_result=predicted,
        typed_score=1.0 if correct else 0.0,
        time_s=time_s,
        extraction_status=parse_status,
        validation_status="validated",
        failure_reason="" if correct else "incorrect",
        trajectory_provenance=trajectory_provenance,
    )


def _benchmark_suite_for_metric(name: str) -> str:
    if name.startswith("bench."):
        parts = name.split(".")
        if len(parts) >= 3:
            return parts[1]
    return "summary"
