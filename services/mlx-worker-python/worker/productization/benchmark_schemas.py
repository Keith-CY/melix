from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from worker.productization.evaluation_schemas import (
    EvaluationJob,
    EvaluationResult,
    EvaluationSample,
    build_evaluation_job_record,
    build_evaluation_result_record,
    build_evaluation_sample_record,
)


_SERVING_BENCHMARK_JOB_SCHEMA_VERSION = "melix.serving_benchmark_job.v1"
_SERVING_BENCHMARK_RESULT_SCHEMA_VERSION = "melix.serving_benchmark_result.v1"


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

    def to_dict(self) -> dict[str, object]:
        return {
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
        }


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

    def to_dict(self) -> dict[str, object]:
        return {
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
        }


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
) -> ServingBenchmarkContextRow:
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
) -> ServingBenchmarkBatchRow:
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
) -> EvaluationSample:
    return build_evaluation_sample_record(
        job_id=job_id,
        suite_id=suite_id,
        dataset_id=dataset_id,
        sample_id=sample_id,
        question=question,
        expected=expected,
        predicted=predicted,
        raw_response=raw_response,
        correct=correct,
        time_s=time_s,
        parse_status=parse_status,
    )


def _benchmark_suite_for_metric(name: str) -> str:
    if name.startswith("bench."):
        parts = name.split(".")
        if len(parts) >= 3:
            return parts[1]
    return "summary"
