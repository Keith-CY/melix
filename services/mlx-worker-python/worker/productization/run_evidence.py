from __future__ import annotations

import heapq
import os
import subprocess
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


RUN_EVIDENCE_SCHEMA_VERSION = "melix.run_evidence.v1"
TELEMETRY_SUMMARY_SCHEMA_VERSION = "melix.telemetry_summary.v1"
PROBE_SUMMARY_SCHEMA_VERSION = "melix.probe_summary.v1"

_BENCHMARK_ROW_PHASES = (
    ("dataset_materialize_ms", "worker", "dataset_materialize"),
    ("prompt_render_ms", "worker", "prompt_render"),
    ("warmup_ms", "cache", "cache_restore"),
    ("prefill_ms", "runtime", "prefill"),
    ("decode_ms", "runtime", "decode"),
)
_EVALUATION_SAMPLE_PHASES = (
    ("sample_render_ms", "worker", "prompt_render"),
    ("inference_ms", "runtime", "decode"),
    ("extraction_ms", "worker", "aggregate_result"),
    ("validation_ms", "worker", "row_execute"),
    ("scoring_ms", "worker", "score_compute"),
)
_EVALUATION_FAILURE_STAGE_PHASES = {
    "inference": "decode",
    "extraction": "aggregate_result",
    "validation": "row_execute",
    "scoring": "score_compute",
}
_EVALUATION_PROBE_SAMPLE_LIMIT_ENV = "MELIX_EVALUATION_PROBE_SAMPLE_LIMIT"
_EVALUATION_PROBE_TOP_N_ENV = "MELIX_EVALUATION_PROBE_TOP_N"
_EVALUATION_PROBE_ANOMALY_LIMIT_ENV = "MELIX_EVALUATION_PROBE_ANOMALY_LIMIT"
_DEFAULT_EVALUATION_PROBE_SAMPLE_LIMIT = 32
_DEFAULT_EVALUATION_PROBE_TOP_N = 10
_DEFAULT_EVALUATION_PROBE_ANOMALY_LIMIT = 24
_MAX_EVALUATION_PROBE_SAMPLE_LIMIT = 512
_EVALUATION_SAMPLE_REASON_PRIORITY = {
    "failed": 0,
    "fallback": 1,
    "skipped": 2,
    "top_duration": 3,
}
_RUNTIME_ATTRIBUTE_KEYS = (
    "runtime_live_model",
    "runtime_model_handle",
    "runtime_kind",
    "runtime_name",
    "runtime_model_id",
    "runtime_model_path",
    "runtime_source_kind",
    "runtime_source_repo",
    "cache_profile",
    "reasoning_mode",
    "structured_output_mode",
    "adapter_id",
    "adapter_snapshot",
    "model_snapshot",
)
_TELEMETRY_FLOAT_FIELDS = (
    "average_cpu_utilization_percent",
    "peak_cpu_utilization_percent",
    "average_p_core_utilization_percent",
    "peak_p_core_utilization_percent",
    "average_e_core_utilization_percent",
    "peak_e_core_utilization_percent",
    "average_gpu_utilization_percent",
    "peak_gpu_utilization_percent",
    "average_gpu_frequency_mhz",
    "peak_gpu_frequency_mhz",
    "average_cpu_power_w",
    "peak_cpu_power_w",
    "average_gpu_power_w",
    "peak_gpu_power_w",
    "average_ane_power_w",
    "peak_ane_power_w",
    "average_dram_power_w",
    "peak_dram_power_w",
    "average_system_power_w",
    "peak_system_power_w",
    "watts_per_output_token",
    "average_process_cpu_percent",
)
_TELEMETRY_INT_FIELDS = (
    "memory_used_bytes",
    "memory_total_bytes",
    "peak_process_memory_bytes",
)
_TELEMETRY_NUMERIC_FIELDS = (*_TELEMETRY_FLOAT_FIELDS, *_TELEMETRY_INT_FIELDS)


class RunEvidenceValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = tuple(errors)
        super().__init__("; ".join(errors))


@dataclass(frozen=True)
class _EvaluationProbeSamplingConfig:
    sample_limit: int
    top_n: int
    anomaly_limit: int


@dataclass
class _EvaluationPhaseAggregate:
    sample_count: int = 0
    total_duration_ms: float = 0.0
    max_duration_ms: float = 0.0
    completed_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0

    def add(self, *, duration_ms: float, status: str) -> None:
        self.sample_count += 1
        self.total_duration_ms += duration_ms
        self.max_duration_ms = max(self.max_duration_ms, duration_ms)
        if status == "failed":
            self.failed_count += 1
        elif status == "skipped":
            self.skipped_count += 1
        else:
            self.completed_count += 1


@dataclass
class _EvaluationSampleCandidate:
    sample_index: int
    payload: dict[str, object]
    total_duration_ms: float
    reasons: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class RunEvidenceMetric:
    name: str
    value: float
    unit: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> RunEvidenceMetric:
        return cls(
            name=str(payload.get("name") or ""),
            value=float(payload.get("value") or 0.0),
            unit=str(payload.get("unit") or ""),
        )


@dataclass(frozen=True)
class RunEvidenceProbe:
    run_id: str
    trace_id: str
    span_id: str
    parent_span_id: str
    component: str
    phase: str
    started_at_monotonic_ms: int
    duration_ms: float
    status: str
    error_stage: str = ""
    error_code: str = ""
    attributes: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "component": self.component,
            "phase": self.phase,
            "started_at_monotonic_ms": self.started_at_monotonic_ms,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "error_stage": self.error_stage,
            "error_code": self.error_code,
            "attributes": dict(self.attributes),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> RunEvidenceProbe:
        attributes = payload.get("attributes")
        return cls(
            run_id=str(payload.get("run_id") or ""),
            trace_id=str(payload.get("trace_id") or ""),
            span_id=str(payload.get("span_id") or ""),
            parent_span_id=str(payload.get("parent_span_id") or ""),
            component=str(payload.get("component") or ""),
            phase=str(payload.get("phase") or ""),
            started_at_monotonic_ms=int(payload.get("started_at_monotonic_ms") or 0),
            duration_ms=float(payload.get("duration_ms") or 0.0),
            status=str(payload.get("status") or ""),
            error_stage=str(payload.get("error_stage") or ""),
            error_code=str(payload.get("error_code") or ""),
            attributes=dict(attributes) if isinstance(attributes, dict) else {},
        )


@dataclass(frozen=True)
class RunEvidenceArtifact:
    kind: str
    path: str
    role: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "path": self.path,
            "role": self.role,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> RunEvidenceArtifact:
        return cls(
            kind=str(payload.get("kind") or ""),
            path=str(payload.get("path") or ""),
            role=str(payload.get("role") or ""),
        )


@dataclass(frozen=True)
class RunEvidenceTelemetrySummary:
    collector_status: str
    telemetry_failures: tuple[str, ...] = ()
    time_series_path: str = ""
    sample_count: int = 0
    average_cpu_utilization_percent: float | None = None
    peak_cpu_utilization_percent: float | None = None
    average_p_core_utilization_percent: float | None = None
    peak_p_core_utilization_percent: float | None = None
    average_e_core_utilization_percent: float | None = None
    peak_e_core_utilization_percent: float | None = None
    average_gpu_utilization_percent: float | None = None
    peak_gpu_utilization_percent: float | None = None
    average_gpu_frequency_mhz: float | None = None
    peak_gpu_frequency_mhz: float | None = None
    average_cpu_power_w: float | None = None
    peak_cpu_power_w: float | None = None
    average_gpu_power_w: float | None = None
    peak_gpu_power_w: float | None = None
    average_ane_power_w: float | None = None
    peak_ane_power_w: float | None = None
    average_dram_power_w: float | None = None
    peak_dram_power_w: float | None = None
    average_system_power_w: float | None = None
    peak_system_power_w: float | None = None
    watts_per_output_token: float | None = None
    memory_used_bytes: int | None = None
    memory_total_bytes: int | None = None
    peak_process_memory_bytes: int | None = None
    average_process_cpu_percent: float | None = None
    thermal_events: tuple[str, ...] = ()
    process_attribution: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": TELEMETRY_SUMMARY_SCHEMA_VERSION,
            "collector_status": self.collector_status,
            "time_series_path": self.time_series_path,
            "telemetry_failures": list(self.telemetry_failures),
            "sample_count": self.sample_count,
            "thermal_events": list(self.thermal_events),
            "process_attribution": dict(self.process_attribution),
        }
        for field_name in _TELEMETRY_NUMERIC_FIELDS:
            value = getattr(self, field_name)
            if value is not None:
                payload[field_name] = value
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> RunEvidenceTelemetrySummary:
        failures = payload.get("telemetry_failures")
        thermal_events = payload.get("thermal_events")
        kwargs: dict[str, object] = {
            field_name: _float_value(payload.get(field_name))
            for field_name in _TELEMETRY_FLOAT_FIELDS
            if payload.get(field_name) is not None
        }
        for field_name in _TELEMETRY_INT_FIELDS:
            if payload.get(field_name) is not None:
                kwargs[field_name] = _int_value(payload.get(field_name))
        return cls(
            collector_status=str(payload.get("collector_status") or ""),
            time_series_path=str(payload.get("time_series_path") or ""),
            telemetry_failures=tuple(str(item) for item in failures) if isinstance(failures, list) else (),
            sample_count=_int_value(payload.get("sample_count")),
            thermal_events=tuple(str(item) for item in thermal_events) if isinstance(thermal_events, list) else (),
            process_attribution=_dict_payload(payload.get("process_attribution")),
            **kwargs,
        )


@dataclass(frozen=True)
class RunEvidenceModelMemorySummary:
    runtime_model_handle: str = ""
    runtime_model_id: str = ""
    runtime_kind: str = ""
    runtime_name: str = ""
    loaded_model_estimated_resident_bytes: int = 0
    runtime_stats_resident_bytes: int = 0
    runtime_stats_model_resident_bytes: int = 0
    runtime_stats_cache_resident_bytes: int = 0
    runtime_stats_kv_cache_bytes: int = 0
    runtime_stats_memory_headroom_bytes: int = 0
    load_triggered_by_run: bool = False
    load_rss_before_bytes: int = 0
    load_rss_after_bytes: int = 0
    load_rss_delta_bytes: int = 0
    measurement_scope: str = "worker_registry"

    def to_dict(self) -> dict[str, object]:
        return {
            "runtime_model_handle": self.runtime_model_handle,
            "runtime_model_id": self.runtime_model_id,
            "runtime_kind": self.runtime_kind,
            "runtime_name": self.runtime_name,
            "loaded_model_estimated_resident_bytes": self.loaded_model_estimated_resident_bytes,
            "runtime_stats_resident_bytes": self.runtime_stats_resident_bytes,
            "runtime_stats_model_resident_bytes": self.runtime_stats_model_resident_bytes,
            "runtime_stats_cache_resident_bytes": self.runtime_stats_cache_resident_bytes,
            "runtime_stats_kv_cache_bytes": self.runtime_stats_kv_cache_bytes,
            "runtime_stats_memory_headroom_bytes": self.runtime_stats_memory_headroom_bytes,
            "load_triggered_by_run": self.load_triggered_by_run,
            "load_rss_before_bytes": self.load_rss_before_bytes,
            "load_rss_after_bytes": self.load_rss_after_bytes,
            "load_rss_delta_bytes": self.load_rss_delta_bytes,
            "measurement_scope": self.measurement_scope,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> RunEvidenceModelMemorySummary:
        return cls(
            runtime_model_handle=str(payload.get("runtime_model_handle") or ""),
            runtime_model_id=str(payload.get("runtime_model_id") or ""),
            runtime_kind=str(payload.get("runtime_kind") or ""),
            runtime_name=str(payload.get("runtime_name") or ""),
            loaded_model_estimated_resident_bytes=_int_value(payload.get("loaded_model_estimated_resident_bytes")),
            runtime_stats_resident_bytes=_int_value(payload.get("runtime_stats_resident_bytes")),
            runtime_stats_model_resident_bytes=_int_value(payload.get("runtime_stats_model_resident_bytes")),
            runtime_stats_cache_resident_bytes=_int_value(payload.get("runtime_stats_cache_resident_bytes")),
            runtime_stats_kv_cache_bytes=_int_value(payload.get("runtime_stats_kv_cache_bytes")),
            runtime_stats_memory_headroom_bytes=_int_value(payload.get("runtime_stats_memory_headroom_bytes")),
            load_triggered_by_run=bool(payload.get("load_triggered_by_run")),
            load_rss_before_bytes=_int_value(payload.get("load_rss_before_bytes")),
            load_rss_after_bytes=_int_value(payload.get("load_rss_after_bytes")),
            load_rss_delta_bytes=_int_value(payload.get("load_rss_delta_bytes")),
            measurement_scope=str(payload.get("measurement_scope") or "worker_registry"),
        )


@dataclass(frozen=True)
class RunEvidenceEnvelope:
    run_id: str
    run_kind: str
    status: str
    command: str
    artifact_root: str
    target_model_id: str
    hf_repo_id: str
    task_kind: str
    suite_id: str
    sample_count: int
    started_at: int
    ended_at: int
    duration_ms: int
    metrics: tuple[RunEvidenceMetric, ...]
    probe_timeline: tuple[RunEvidenceProbe, ...]
    telemetry_summary: RunEvidenceTelemetrySummary
    model_memory_summary: RunEvidenceModelMemorySummary
    artifacts: tuple[RunEvidenceArtifact, ...]
    melix_commit: str = ""
    git_branch: str = ""
    dirty_worktree: bool = False
    model_snapshot: str = ""
    adapter_id: str = ""
    adapter_snapshot: str = ""
    runtime_kind: str = ""
    runtime_config: dict[str, object] = field(default_factory=dict)
    dataset_ref: str = ""
    dataset_revision: str = ""
    input_digest: str = ""
    prompt_template_digest: str = ""
    generation_config: dict[str, object] = field(default_factory=dict)
    failure_summary: dict[str, object] = field(default_factory=dict)
    fallback_summary: dict[str, object] = field(default_factory=dict)
    domain_results: dict[str, object] = field(default_factory=dict)
    schema_version: str = RUN_EVIDENCE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "melix_commit": self.melix_commit,
            "git_branch": self.git_branch,
            "dirty_worktree": self.dirty_worktree,
            "run_kind": self.run_kind,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "command": self.command,
            "artifact_root": self.artifact_root,
            "target_model_id": self.target_model_id,
            "hf_repo_id": self.hf_repo_id,
            "task_kind": self.task_kind,
            "model_snapshot": self.model_snapshot,
            "adapter_id": self.adapter_id,
            "adapter_snapshot": self.adapter_snapshot,
            "runtime_kind": self.runtime_kind,
            "runtime_config": dict(self.runtime_config),
            "dataset_ref": self.dataset_ref,
            "dataset_revision": self.dataset_revision,
            "suite_id": self.suite_id,
            "sample_count": self.sample_count,
            "input_digest": self.input_digest,
            "prompt_template_digest": self.prompt_template_digest,
            "generation_config": dict(self.generation_config),
            "metrics": [metric.to_dict() for metric in self.metrics],
            "probe_timeline": [probe.to_dict() for probe in self.probe_timeline],
            "telemetry_summary": self.telemetry_summary.to_dict(),
            "model_memory_summary": self.model_memory_summary.to_dict(),
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "failure_summary": dict(self.failure_summary),
            "fallback_summary": dict(self.fallback_summary),
            "domain_results": dict(self.domain_results),
        }
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> RunEvidenceEnvelope:
        metrics = payload.get("metrics")
        probes = payload.get("probe_timeline")
        artifacts = payload.get("artifacts")
        telemetry = payload.get("telemetry_summary")
        model_memory = payload.get("model_memory_summary")
        return cls(
            schema_version=str(payload.get("schema_version") or ""),
            run_id=str(payload.get("run_id") or ""),
            melix_commit=str(payload.get("melix_commit") or ""),
            git_branch=str(payload.get("git_branch") or ""),
            dirty_worktree=bool(payload.get("dirty_worktree")),
            run_kind=str(payload.get("run_kind") or ""),
            started_at=int(payload.get("started_at") or 0),
            ended_at=int(payload.get("ended_at") or 0),
            duration_ms=int(payload.get("duration_ms") or 0),
            status=str(payload.get("status") or ""),
            command=str(payload.get("command") or ""),
            artifact_root=str(payload.get("artifact_root") or ""),
            target_model_id=str(payload.get("target_model_id") or ""),
            hf_repo_id=str(payload.get("hf_repo_id") or ""),
            task_kind=str(payload.get("task_kind") or ""),
            model_snapshot=str(payload.get("model_snapshot") or ""),
            adapter_id=str(payload.get("adapter_id") or ""),
            adapter_snapshot=str(payload.get("adapter_snapshot") or ""),
            runtime_kind=str(payload.get("runtime_kind") or ""),
            runtime_config=_dict_payload(payload.get("runtime_config")),
            dataset_ref=str(payload.get("dataset_ref") or ""),
            dataset_revision=str(payload.get("dataset_revision") or ""),
            suite_id=str(payload.get("suite_id") or ""),
            sample_count=int(payload.get("sample_count") or 0),
            input_digest=str(payload.get("input_digest") or ""),
            prompt_template_digest=str(payload.get("prompt_template_digest") or ""),
            generation_config=_dict_payload(payload.get("generation_config")),
            metrics=tuple(
                RunEvidenceMetric.from_dict(item)
                for item in metrics
                if isinstance(item, dict)
            ) if isinstance(metrics, list) else (),
            probe_timeline=tuple(
                RunEvidenceProbe.from_dict(item)
                for item in probes
                if isinstance(item, dict)
            ) if isinstance(probes, list) else (),
            telemetry_summary=RunEvidenceTelemetrySummary.from_dict(telemetry)
            if isinstance(telemetry, dict)
            else RunEvidenceTelemetrySummary(collector_status=""),
            model_memory_summary=RunEvidenceModelMemorySummary.from_dict(model_memory)
            if isinstance(model_memory, dict)
            else RunEvidenceModelMemorySummary(),
            artifacts=tuple(
                RunEvidenceArtifact.from_dict(item)
                for item in artifacts
                if isinstance(item, dict)
            ) if isinstance(artifacts, list) else (),
            failure_summary=_dict_payload(payload.get("failure_summary")),
            fallback_summary=_dict_payload(payload.get("fallback_summary")),
            domain_results=_dict_payload(payload.get("domain_results")),
        )


def default_telemetry_summary() -> RunEvidenceTelemetrySummary:
    return RunEvidenceTelemetrySummary(
        collector_status="failed",
        telemetry_failures=(
            "apple_silicon_telemetry_collection_missing",
        ),
    )


def default_model_memory_summary() -> RunEvidenceModelMemorySummary:
    return RunEvidenceModelMemorySummary()


def _model_memory_summary(
    summary: RunEvidenceModelMemorySummary | dict[str, object] | None,
) -> RunEvidenceModelMemorySummary:
    if isinstance(summary, RunEvidenceModelMemorySummary):
        return summary
    if isinstance(summary, dict):
        return RunEvidenceModelMemorySummary.from_dict(summary)
    return default_model_memory_summary()


def build_serving_benchmark_run_evidence(
    *,
    job: Any,
    results: tuple[Any, ...],
    artifact_root: Path,
    artifact_paths: dict[str, Path],
    artifact_write_started_at_monotonic_ms: int,
    artifact_write_duration_ms: float,
    context_rows: Iterable[dict[str, object]] = (),
    batch_rows: Iterable[dict[str, object]] = (),
    telemetry_summary: RunEvidenceTelemetrySummary | None = None,
    telemetry_probes: Iterable[RunEvidenceProbe] = (),
    model_memory_summary: RunEvidenceModelMemorySummary | dict[str, object] | None = None,
    command: str = "melix bench run",
    repo_root: Path | None = None,
) -> RunEvidenceEnvelope:
    commit, branch, dirty = git_identity(repo_root)
    metrics = tuple(
        RunEvidenceMetric(name=metric.name, value=float(metric.value), unit=metric.unit)
        for result in results
        for metric in result.metrics
    )
    artifacts = tuple(
        RunEvidenceArtifact(kind=kind, path=_artifact_path(path, artifact_root), role=kind)
        for kind, path in sorted(artifact_paths.items())
    )
    run_started_at_monotonic_ms = _run_started_at_monotonic_ms(
        artifact_write_started_at_monotonic_ms=artifact_write_started_at_monotonic_ms,
        duration_ms=max(int(job.updated_at_unix_ms) - int(job.created_at_unix_ms), 0),
    )
    trace_id = _trace_id(job.job_id)
    root_span_id = _span_id(job.job_id, "worker_dispatch")
    runtime_attributes = _runtime_attributes(job.parameters)
    probe_timeline = (
        _run_root_probe(
            run_id=job.job_id,
            trace_id=trace_id,
            started_at_monotonic_ms=run_started_at_monotonic_ms,
            duration_ms=max(int(job.updated_at_unix_ms) - int(job.created_at_unix_ms), 0),
        ),
        _runtime_prepare_probe(
            run_id=job.job_id,
            trace_id=trace_id,
            parent_span_id=root_span_id,
            started_at_monotonic_ms=run_started_at_monotonic_ms,
            attributes=runtime_attributes,
        ),
        _adapter_probe(
            run_id=job.job_id,
            trace_id=trace_id,
            parent_span_id=root_span_id,
            started_at_monotonic_ms=run_started_at_monotonic_ms,
            adapter_id=str(job.parameters.get("adapter_id", "")),
            adapter_snapshot=str(job.parameters.get("adapter_snapshot", "")),
        ),
        *build_benchmark_stage_probes(
            run_id=job.job_id,
            trace_id=trace_id,
            parent_span_id=root_span_id,
            started_at_monotonic_ms=run_started_at_monotonic_ms + 1,
            rows=(*tuple(context_rows), *tuple(batch_rows)),
        ),
        *tuple(telemetry_probes),
        artifact_write_probe(
            run_id=job.job_id,
            trace_id=trace_id,
            parent_span_id=root_span_id,
            started_at_monotonic_ms=artifact_write_started_at_monotonic_ms,
            duration_ms=artifact_write_duration_ms,
            artifact_count=len(artifacts),
        ),
    )
    return RunEvidenceEnvelope(
        run_id=job.job_id,
        melix_commit=commit,
        git_branch=branch,
        dirty_worktree=dirty,
        run_kind="serving_benchmark",
        started_at=int(job.created_at_unix_ms),
        ended_at=int(job.updated_at_unix_ms),
        duration_ms=max(int(job.updated_at_unix_ms) - int(job.created_at_unix_ms), 0),
        status=job.status,
        command=command,
        artifact_root=str(artifact_root),
        target_model_id=job.model_id,
        hf_repo_id=job.source_repo,
        task_kind=job.task_kind,
        model_snapshot=str(job.parameters.get("model_snapshot", "")),
        adapter_id=str(job.parameters.get("adapter_id", "")),
        adapter_snapshot=str(job.parameters.get("adapter_snapshot", "")),
        runtime_kind=str(job.parameters.get("runtime_kind", "")),
        runtime_config={
            "cache_profile": job.cache_profile,
            "reasoning_mode": job.reasoning_mode,
            "structured_output_mode": job.structured_output_mode,
        },
        dataset_ref=str(job.parameters.get("dataset_ref", job.source_repo)),
        dataset_revision=str(job.parameters.get("dataset_revision", "")),
        suite_id=",".join(job.suites),
        sample_count=_benchmark_sample_count(job),
        input_digest=str(job.parameters.get("input_digest", "")),
        prompt_template_digest=str(job.parameters.get("prompt_template_digest", "")),
        generation_config={
            "context_lengths": list(job.context_lengths),
            "generation_length": job.generation_length,
            "batch_sizes": list(job.batch_sizes),
            "repeats": job.repeats,
        },
        metrics=metrics,
        probe_timeline=probe_timeline,
        telemetry_summary=telemetry_summary or default_telemetry_summary(),
        model_memory_summary=_model_memory_summary(model_memory_summary),
        artifacts=artifacts,
        failure_summary=_failure_summary(job.status),
        fallback_summary=_fallback_summary(job.parameters),
        domain_results={
            "serving_benchmark": {
                "job": job.to_dict(),
                "results": [result.to_dict() for result in results],
            },
        },
    )


def build_evaluation_run_evidence(
    *,
    job: Any,
    result: Any,
    sample_count: int,
    artifact_root: Path,
    artifact_paths: dict[str, Path],
    artifact_write_started_at_monotonic_ms: int,
    artifact_write_duration_ms: float,
    samples: Iterable[Any] = (),
    telemetry_summary: RunEvidenceTelemetrySummary | None = None,
    telemetry_probes: Iterable[RunEvidenceProbe] = (),
    model_memory_summary: RunEvidenceModelMemorySummary | dict[str, object] | None = None,
    command: str = "melix eval run",
    repo_root: Path | None = None,
) -> RunEvidenceEnvelope:
    commit, branch, dirty = git_identity(repo_root)
    metrics = tuple(
        RunEvidenceMetric(name=metric.name, value=float(metric.value), unit=metric.unit)
        for metric in result.metrics
    )
    artifacts = tuple(
        RunEvidenceArtifact(kind=kind, path=_artifact_path(path, artifact_root), role=kind)
        for kind, path in sorted(artifact_paths.items())
    )
    run_started_at_monotonic_ms = _run_started_at_monotonic_ms(
        artifact_write_started_at_monotonic_ms=artifact_write_started_at_monotonic_ms,
        duration_ms=max(int(job.updated_at_unix_ms) - int(job.created_at_unix_ms), 0),
    )
    trace_id = _trace_id(job.job_id)
    root_span_id = _span_id(job.job_id, "worker_dispatch")
    runtime_attributes = _runtime_attributes(job.parameters)
    probe_timeline = (
        _run_root_probe(
            run_id=job.job_id,
            trace_id=trace_id,
            started_at_monotonic_ms=run_started_at_monotonic_ms,
            duration_ms=max(int(job.updated_at_unix_ms) - int(job.created_at_unix_ms), 0),
        ),
        _runtime_prepare_probe(
            run_id=job.job_id,
            trace_id=trace_id,
            parent_span_id=root_span_id,
            started_at_monotonic_ms=run_started_at_monotonic_ms,
            attributes=runtime_attributes,
        ),
        _adapter_probe(
            run_id=job.job_id,
            trace_id=trace_id,
            parent_span_id=root_span_id,
            started_at_monotonic_ms=run_started_at_monotonic_ms,
            adapter_id=str(job.parameters.get("adapter_id", "")),
            adapter_snapshot=str(job.parameters.get("adapter_snapshot", "")),
        ),
        *build_evaluation_stage_probes(
            run_id=job.job_id,
            trace_id=trace_id,
            parent_span_id=root_span_id,
            started_at_monotonic_ms=run_started_at_monotonic_ms + 1,
            samples=samples,
        ),
        *tuple(telemetry_probes),
        artifact_write_probe(
            run_id=job.job_id,
            trace_id=trace_id,
            parent_span_id=root_span_id,
            started_at_monotonic_ms=artifact_write_started_at_monotonic_ms,
            duration_ms=artifact_write_duration_ms,
            artifact_count=len(artifacts),
        ),
    )
    return RunEvidenceEnvelope(
        run_id=job.job_id,
        melix_commit=commit,
        git_branch=branch,
        dirty_worktree=dirty,
        run_kind="evaluation",
        started_at=int(job.created_at_unix_ms),
        ended_at=int(job.updated_at_unix_ms),
        duration_ms=max(int(job.updated_at_unix_ms) - int(job.created_at_unix_ms), 0),
        status=job.status,
        command=command,
        artifact_root=str(artifact_root),
        target_model_id=job.model_id,
        hf_repo_id=job.source_repo,
        task_kind=job.task_kind,
        model_snapshot=str(job.parameters.get("model_snapshot", "")),
        adapter_id=str(job.parameters.get("adapter_id", "")),
        adapter_snapshot=str(job.parameters.get("adapter_snapshot", "")),
        runtime_kind=str(job.parameters.get("runtime_kind", "")),
        runtime_config={"scoring_mode": job.scoring_mode},
        dataset_ref=job.dataset_id,
        dataset_revision=str(job.parameters.get("dataset_revision", "")),
        suite_id=job.suite_id,
        sample_count=sample_count,
        input_digest=str(job.parameters.get("input_digest", "")),
        prompt_template_digest=str(job.parameters.get("prompt_template_digest", "")),
        generation_config={
            "few_shot": job.few_shot,
            "seed": job.seed,
            "code_exec_policy": job.code_exec_policy,
        },
        metrics=metrics,
        probe_timeline=probe_timeline,
        telemetry_summary=telemetry_summary or default_telemetry_summary(),
        model_memory_summary=_model_memory_summary(model_memory_summary),
        artifacts=artifacts,
        failure_summary=_failure_summary(job.status, failure_count=result.failure_count),
        fallback_summary=_fallback_summary(job.parameters),
        domain_results={
            "evaluation": {
                "job": job.to_dict(),
                "result": result.to_dict(),
                "sample_count": sample_count,
            },
        },
    )


def build_benchmark_stage_probes(
    *,
    run_id: str,
    trace_id: str,
    parent_span_id: str,
    started_at_monotonic_ms: int,
    rows: Iterable[dict[str, object]],
) -> tuple[RunEvidenceProbe, ...]:
    probes: list[RunEvidenceProbe] = []
    cursor = started_at_monotonic_ms
    for row_index, row in enumerate(rows):
        attributes = _benchmark_probe_attributes(row=row, row_index=row_index)
        cache_hit = _bool_value(row.get("cache_hit"))
        probes.append(
            _stage_probe(
                run_id=run_id,
                trace_id=trace_id,
                parent_span_id=parent_span_id,
                component="cache",
                phase="cache_lookup",
                started_at_monotonic_ms=cursor,
                duration_ms=0.001,
                status="completed",
                attributes={**attributes, "cache_hit": cache_hit},
            )
        )
        cursor += 1
        for field_name, component, phase in _BENCHMARK_ROW_PHASES:
            duration_ms = _float_value(row.get(field_name))
            if field_name == "warmup_ms" and not cache_hit:
                status = "skipped"
            else:
                status = "completed" if duration_ms > 0.0 else "skipped"
            probes.append(
                _stage_probe(
                    run_id=run_id,
                    trace_id=trace_id,
                    parent_span_id=parent_span_id,
                    component=component,
                    phase=phase,
                    started_at_monotonic_ms=cursor,
                    duration_ms=duration_ms,
                    status=status,
                    attributes={**attributes, "source_field": field_name},
                )
            )
            cursor += max(int(duration_ms), 1)
        fallback_count = _int_value(row.get("speculative_fallback_count")) + _int_value(row.get("dflash_rollback_count"))
        if fallback_count > 0:
            probes.append(
                _stage_probe(
                    run_id=run_id,
                    trace_id=trace_id,
                    parent_span_id=parent_span_id,
                    component="runtime",
                    phase="fallback_enter",
                    started_at_monotonic_ms=cursor,
                    duration_ms=0.001,
                    status="completed",
                    attributes={**attributes, "fallback_count": fallback_count},
                )
            )
            cursor += 1
    return tuple(probes)


def build_evaluation_stage_probes(
    *,
    run_id: str,
    trace_id: str,
    parent_span_id: str,
    started_at_monotonic_ms: int,
    samples: Iterable[Any],
    sample_limit: int | None = None,
    top_n: int | None = None,
    anomaly_limit: int | None = None,
) -> tuple[RunEvidenceProbe, ...]:
    config = _evaluation_probe_sampling_config(
        sample_limit=sample_limit,
        top_n=top_n,
        anomaly_limit=anomaly_limit,
    )
    probes: list[RunEvidenceProbe] = []
    cursor = started_at_monotonic_ms
    phase_aggregates = {
        phase: _EvaluationPhaseAggregate()
        for _field_name, _component, phase in _EVALUATION_SAMPLE_PHASES
    }
    sample_count = 0
    failed_sample_count = 0
    skipped_sample_count = 0
    fallback_sample_count = 0
    selected_candidates: dict[int, _EvaluationSampleCandidate] = {}
    anomaly_candidate_counts = {"failed": 0, "skipped": 0, "fallback": 0}
    top_candidates: list[tuple[float, int, dict[str, object]]] = []

    for sample_index, sample in enumerate(samples):
        payload = _object_payload(sample)
        failure_stage = str(payload.get("failure_stage", "")).strip()
        phase_rows = _evaluation_sample_phase_rows(payload=payload)
        sample_total_duration_ms = sum(row["duration_ms"] for row in phase_rows)
        sample_failed = any(row["status"] == "failed" for row in phase_rows)
        sample_skipped = any(row["status"] == "skipped" for row in phase_rows)
        sample_fallback = failure_stage == "fallback"
        sample_count += 1
        failed_sample_count += int(sample_failed)
        skipped_sample_count += int(sample_skipped)
        fallback_sample_count += int(sample_fallback)

        for row in phase_rows:
            phase_aggregates[str(row["phase"])].add(
                duration_ms=float(row["duration_ms"]),
                status=str(row["status"]),
            )

        if config.top_n > 0:
            _remember_top_evaluation_sample(
                top_candidates,
                limit=config.top_n,
                sample_index=sample_index,
                payload=payload,
                total_duration_ms=sample_total_duration_ms,
            )
        if config.anomaly_limit > 0:
            if sample_failed and anomaly_candidate_counts["failed"] < config.anomaly_limit:
                _merge_evaluation_sample_candidate(
                    selected_candidates,
                    sample_index=sample_index,
                    payload=payload,
                    total_duration_ms=sample_total_duration_ms,
                    reason="failed",
                )
                anomaly_candidate_counts["failed"] += 1
            if sample_fallback and anomaly_candidate_counts["fallback"] < config.anomaly_limit:
                _merge_evaluation_sample_candidate(
                    selected_candidates,
                    sample_index=sample_index,
                    payload=payload,
                    total_duration_ms=sample_total_duration_ms,
                    reason="fallback",
                )
                anomaly_candidate_counts["fallback"] += 1
            if sample_skipped and anomaly_candidate_counts["skipped"] < config.anomaly_limit:
                _merge_evaluation_sample_candidate(
                    selected_candidates,
                    sample_index=sample_index,
                    payload=payload,
                    total_duration_ms=sample_total_duration_ms,
                    reason="skipped",
                )
                anomaly_candidate_counts["skipped"] += 1

    if sample_count == 0:
        return ()

    for total_duration_ms, sample_index, payload in sorted(
        top_candidates,
        key=lambda item: (-item[0], item[1]),
    ):
        _merge_evaluation_sample_candidate(
            selected_candidates,
            sample_index=sample_index,
            payload=payload,
            total_duration_ms=total_duration_ms,
            reason="top_duration",
        )

    selected_samples = _bounded_evaluation_sample_candidates(
        selected_candidates.values(),
        limit=config.sample_limit,
    )
    probes.append(
        _stage_probe(
            run_id=run_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            component="worker",
            phase="sample_select",
            started_at_monotonic_ms=cursor,
            duration_ms=0.001,
            status="completed",
            attributes={
                "probe_kind": "aggregate_summary",
                "sample_count": sample_count,
                "sample_detail_limit": config.sample_limit,
                "sample_detail_count": len(selected_samples),
                "top_n": config.top_n,
                "anomaly_limit": config.anomaly_limit,
                "failed_sample_count": failed_sample_count,
                "skipped_sample_count": skipped_sample_count,
                "fallback_sample_count": fallback_sample_count,
            },
        )
    )
    cursor += 1
    for field_name, component, phase in _EVALUATION_SAMPLE_PHASES:
        aggregate = phase_aggregates[phase]
        probes.append(
            _stage_probe(
                run_id=run_id,
                trace_id=trace_id,
                parent_span_id=parent_span_id,
                component=component,
                phase=phase,
                started_at_monotonic_ms=cursor,
                duration_ms=aggregate.total_duration_ms,
                status=_evaluation_aggregate_status(aggregate),
                attributes={
                    "probe_kind": "aggregate_summary",
                    "source_field": field_name,
                    "sample_count": aggregate.sample_count,
                    "completed_count": aggregate.completed_count,
                    "failed_count": aggregate.failed_count,
                    "skipped_count": aggregate.skipped_count,
                    "duration_total_ms": round(aggregate.total_duration_ms, 6),
                    "duration_mean_ms": round(
                        aggregate.total_duration_ms / aggregate.sample_count,
                        6,
                    ) if aggregate.sample_count else 0.0,
                    "duration_max_ms": round(aggregate.max_duration_ms, 6),
                },
            )
        )
        cursor += max(int(aggregate.total_duration_ms), 1)
    if fallback_sample_count:
        probes.append(
            _stage_probe(
                run_id=run_id,
                trace_id=trace_id,
                parent_span_id=parent_span_id,
                component="runtime",
                phase="fallback_enter",
                started_at_monotonic_ms=cursor,
                duration_ms=0.001,
                status="completed",
                attributes={
                    "probe_kind": "aggregate_summary",
                    "sample_count": sample_count,
                    "fallback_sample_count": fallback_sample_count,
                },
            )
        )
        cursor += 1

    for candidate in selected_samples:
        cursor = _append_evaluation_sample_detail_probes(
            probes,
            run_id=run_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            started_at_monotonic_ms=cursor,
            candidate=candidate,
        )
    return tuple(probes)


def _append_evaluation_sample_detail_probes(
    probes: list[RunEvidenceProbe],
    *,
    run_id: str,
    trace_id: str,
    parent_span_id: str,
    started_at_monotonic_ms: int,
    candidate: _EvaluationSampleCandidate,
) -> int:
    cursor = started_at_monotonic_ms
    payload = candidate.payload
    attributes = {
        **_evaluation_probe_attributes(
            payload=payload,
            sample_index=candidate.sample_index,
        ),
        "probe_kind": "sample_detail",
        "sample_probe_reason": _evaluation_sample_reason_label(candidate.reasons),
        "sample_total_duration_ms": round(candidate.total_duration_ms, 6),
    }
    probes.append(
        _stage_probe(
            run_id=run_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            component="worker",
            phase="sample_select",
            started_at_monotonic_ms=cursor,
            duration_ms=0.001,
            status="completed",
            attributes=attributes,
        )
    )
    cursor += 1
    for row in _evaluation_sample_phase_rows(payload=payload):
        probes.append(
            _stage_probe(
                run_id=run_id,
                trace_id=trace_id,
                parent_span_id=parent_span_id,
                component=str(row["component"]),
                phase=str(row["phase"]),
                started_at_monotonic_ms=cursor,
                duration_ms=float(row["duration_ms"]),
                status=str(row["status"]),
                error_stage=str(row["error_stage"]),
                error_code=str(row["error_code"]),
                attributes={**attributes, "source_field": str(row["source_field"])},
            )
        )
        cursor += max(int(float(row["duration_ms"])), 1)
    if str(payload.get("failure_stage", "")).strip() == "fallback":
        probes.append(
            _stage_probe(
                run_id=run_id,
                trace_id=trace_id,
                parent_span_id=parent_span_id,
                component="runtime",
                phase="fallback_enter",
                started_at_monotonic_ms=cursor,
                duration_ms=0.001,
                status="completed",
                attributes=attributes,
            )
        )
        cursor += 1
    return cursor


def _evaluation_sample_phase_rows(payload: dict[str, object]) -> tuple[dict[str, object], ...]:
    failure_stage = str(payload.get("failure_stage", "")).strip()
    failure_reason = str(payload.get("failure_reason", "") or "")
    rows: list[dict[str, object]] = []
    for field_name, component, phase in _EVALUATION_SAMPLE_PHASES:
        duration_ms = _float_value(payload.get(field_name))
        failed = _evaluation_probe_failed(
            failure_stage=failure_stage,
            field_name=field_name,
            phase=phase,
        )
        status = "failed" if failed else ("completed" if duration_ms > 0.0 else "skipped")
        rows.append(
            {
                "source_field": field_name,
                "component": component,
                "phase": phase,
                "duration_ms": duration_ms,
                "status": status,
                "error_stage": phase if failed else "",
                "error_code": failure_reason if failed else "",
            }
        )
    return tuple(rows)


def _evaluation_probe_sampling_config(
    *,
    sample_limit: int | None,
    top_n: int | None,
    anomaly_limit: int | None,
) -> _EvaluationProbeSamplingConfig:
    resolved_sample_limit = _bounded_int_config(
        explicit=sample_limit,
        env_name=_EVALUATION_PROBE_SAMPLE_LIMIT_ENV,
        default=_DEFAULT_EVALUATION_PROBE_SAMPLE_LIMIT,
        minimum=0,
        maximum=_MAX_EVALUATION_PROBE_SAMPLE_LIMIT,
    )
    resolved_top_n = _bounded_int_config(
        explicit=top_n,
        env_name=_EVALUATION_PROBE_TOP_N_ENV,
        default=_DEFAULT_EVALUATION_PROBE_TOP_N,
        minimum=0,
        maximum=resolved_sample_limit,
    )
    resolved_anomaly_limit = _bounded_int_config(
        explicit=anomaly_limit,
        env_name=_EVALUATION_PROBE_ANOMALY_LIMIT_ENV,
        default=_DEFAULT_EVALUATION_PROBE_ANOMALY_LIMIT,
        minimum=0,
        maximum=resolved_sample_limit,
    )
    return _EvaluationProbeSamplingConfig(
        sample_limit=resolved_sample_limit,
        top_n=resolved_top_n,
        anomaly_limit=resolved_anomaly_limit,
    )


def _bounded_int_config(
    *,
    explicit: int | None,
    env_name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw_value: object = explicit
    if raw_value is None:
        raw_value = os.environ.get(env_name, "")
    if raw_value in ("", None):
        parsed = default
    else:
        try:
            parsed = int(raw_value)
        except (TypeError, ValueError):
            parsed = default
    return min(max(parsed, minimum), maximum)


def _remember_top_evaluation_sample(
    top_candidates: list[tuple[float, int, dict[str, object]]],
    *,
    limit: int,
    sample_index: int,
    payload: dict[str, object],
    total_duration_ms: float,
) -> None:
    if limit <= 0:
        return
    candidate = (total_duration_ms, sample_index, payload)
    if len(top_candidates) < limit:
        heapq.heappush(top_candidates, candidate)
    elif total_duration_ms > top_candidates[0][0]:
        heapq.heapreplace(top_candidates, candidate)


def _merge_evaluation_sample_candidate(
    candidates: dict[int, _EvaluationSampleCandidate],
    *,
    sample_index: int,
    payload: dict[str, object],
    total_duration_ms: float,
    reason: str,
) -> None:
    candidate = candidates.get(sample_index)
    if candidate is None:
        candidate = _EvaluationSampleCandidate(
            sample_index=sample_index,
            payload=payload,
            total_duration_ms=total_duration_ms,
        )
        candidates[sample_index] = candidate
    else:
        candidate.total_duration_ms = max(candidate.total_duration_ms, total_duration_ms)
    candidate.reasons.add(reason)


def _bounded_evaluation_sample_candidates(
    candidates: Iterable[_EvaluationSampleCandidate],
    *,
    limit: int,
) -> tuple[_EvaluationSampleCandidate, ...]:
    if limit <= 0:
        return ()
    return tuple(
        sorted(candidates, key=_evaluation_sample_candidate_sort_key)[:limit]
    )


def _evaluation_sample_candidate_sort_key(
    candidate: _EvaluationSampleCandidate,
) -> tuple[int, float, int]:
    reason_priority = min(
        (
            _EVALUATION_SAMPLE_REASON_PRIORITY.get(reason, 99)
            for reason in candidate.reasons
        ),
        default=99,
    )
    return (reason_priority, -candidate.total_duration_ms, candidate.sample_index)


def _evaluation_sample_reason_label(reasons: set[str]) -> str:
    return ",".join(
        sorted(
            reasons,
            key=lambda reason: _EVALUATION_SAMPLE_REASON_PRIORITY.get(reason, 99),
        )
    )


def _evaluation_aggregate_status(aggregate: _EvaluationPhaseAggregate) -> str:
    if aggregate.completed_count > 0:
        return "completed"
    if aggregate.failed_count > 0:
        return "failed"
    return "skipped"


def artifact_write_probe(
    *,
    run_id: str,
    trace_id: str | None = None,
    parent_span_id: str = "",
    started_at_monotonic_ms: int,
    duration_ms: float,
    artifact_count: int,
) -> RunEvidenceProbe:
    return RunEvidenceProbe(
        run_id=run_id,
        trace_id=trace_id or _trace_id(run_id),
        span_id=_span_id(run_id, "artifact_write"),
        parent_span_id=parent_span_id,
        component="report",
        phase="artifact_write",
        started_at_monotonic_ms=started_at_monotonic_ms,
        duration_ms=max(duration_ms, 0.001),
        status="completed",
        attributes={"artifact_count": artifact_count},
    )


def summarize_probe_timeline(probes: Iterable[RunEvidenceProbe | dict[str, object]]) -> dict[str, object]:
    normalized = [
        probe if isinstance(probe, RunEvidenceProbe) else RunEvidenceProbe.from_dict(probe)
        for probe in probes
        if isinstance(probe, (RunEvidenceProbe, dict))
    ]
    component_durations: dict[str, float] = {}
    for probe in normalized:
        if probe.attributes.get("probe_kind") == "sample_detail":
            continue
        component_durations[probe.component] = round(
            component_durations.get(probe.component, 0.0) + probe.duration_ms,
            6,
        )
    return {
        "schema_version": PROBE_SUMMARY_SCHEMA_VERSION,
        "probe_count": len(normalized),
        "component_duration_ms": dict(sorted(component_durations.items())),
        "slowest_phases": [
            _probe_summary_row(probe)
            for probe in sorted(normalized, key=lambda item: item.duration_ms, reverse=True)[:5]
        ],
        "failed_phases": [
            _probe_summary_row(probe)
            for probe in normalized
            if probe.status == "failed"
        ],
        "skipped_phases": [
            _probe_summary_row(probe)
            for probe in normalized
            if probe.status == "skipped"
        ][:10],
        "fallback_phases": [
            _probe_summary_row(probe)
            for probe in normalized
            if probe.phase in {"fallback_enter", "fallback_exit"}
        ],
    }


def summarize_run_evidence_probes(run_evidence: Iterable[dict[str, object]]) -> dict[str, object]:
    run_summaries: list[dict[str, object]] = []
    all_probes: list[RunEvidenceProbe] = []
    for payload in run_evidence:
        if not isinstance(payload, dict):
            continue
        probes = [
            RunEvidenceProbe.from_dict(item)
            for item in payload.get("probe_timeline", [])
            if isinstance(item, dict)
        ]
        all_probes.extend(probes)
        summary = summarize_probe_timeline(probes)
        summary["run_id"] = str(payload.get("run_id", ""))
        summary["run_kind"] = str(payload.get("run_kind", ""))
        run_summaries.append(summary)
    combined = summarize_probe_timeline(all_probes)
    combined["runs"] = run_summaries
    return combined


def git_identity(repo_root: Path | None = None) -> tuple[str, str, bool]:
    env_commit = os.environ.get("MELIX_GIT_COMMIT", "").strip()
    env_branch = os.environ.get("MELIX_GIT_BRANCH", "").strip()
    if env_commit and env_branch:
        dirty = os.environ.get("MELIX_GIT_DIRTY", "").strip().lower() in {"1", "true", "yes"}
        return env_commit, env_branch, dirty

    root = repo_root or Path.cwd()
    try:
        commit = _git_output(root, "rev-parse", "HEAD")
        branch = _git_output(root, "branch", "--show-current") or "detached"
        dirty = bool(_git_output(root, "status", "--short"))
        return commit, branch, dirty
    except (OSError, subprocess.CalledProcessError):
        return env_commit or "unknown", env_branch or "unknown", True


def validate_run_evidence_payload(payload: dict[str, object]) -> list[str]:
    errors: list[str] = []
    required_fields = (
        "schema_version",
        "run_id",
        "melix_commit",
        "git_branch",
        "dirty_worktree",
        "run_kind",
        "started_at",
        "ended_at",
        "duration_ms",
        "status",
        "command",
        "artifact_root",
        "target_model_id",
        "hf_repo_id",
        "task_kind",
        "model_snapshot",
        "adapter_id",
        "adapter_snapshot",
        "runtime_kind",
        "runtime_config",
        "dataset_ref",
        "dataset_revision",
        "suite_id",
        "sample_count",
        "input_digest",
        "prompt_template_digest",
        "generation_config",
        "metrics",
        "probe_timeline",
        "telemetry_summary",
        "model_memory_summary",
        "artifacts",
        "failure_summary",
        "fallback_summary",
    )
    for field_name in required_fields:
        if field_name not in payload:
            errors.append(f"missing required evidence field: {field_name}")

    if payload.get("schema_version") != RUN_EVIDENCE_SCHEMA_VERSION:
        errors.append("schema_version must be melix.run_evidence.v1")
    for field_name in ("run_id", "run_kind", "status", "artifact_root", "target_model_id", "task_kind", "suite_id"):
        if field_name in payload and not str(payload.get(field_name) or "").strip():
            errors.append(f"required evidence field is empty: {field_name}")
    if not isinstance(payload.get("dirty_worktree"), bool):
        errors.append("dirty_worktree must be boolean")
    if not isinstance(payload.get("runtime_config"), dict):
        errors.append("runtime_config must be an object")
    if not isinstance(payload.get("generation_config"), dict):
        errors.append("generation_config must be an object")
    if not isinstance(payload.get("metrics"), list):
        errors.append("metrics must be a list")
    if not isinstance(payload.get("probe_timeline"), list) or not payload.get("probe_timeline"):
        errors.append("probe_timeline must be a non-empty list")
    if not isinstance(payload.get("telemetry_summary"), dict):
        errors.append("telemetry_summary must be an object")
    if "model_memory_summary" in payload and not isinstance(payload.get("model_memory_summary"), dict):
        errors.append("model_memory_summary must be an object")
    if not isinstance(payload.get("artifacts"), list) or not payload.get("artifacts"):
        errors.append("artifacts must be a non-empty list")
    if not isinstance(payload.get("failure_summary"), dict):
        errors.append("failure_summary must be an object")
    if not isinstance(payload.get("fallback_summary"), dict):
        errors.append("fallback_summary must be an object")
    return errors


def assert_valid_run_evidence_payload(payload: dict[str, object]) -> None:
    errors = validate_run_evidence_payload(payload)
    if errors:
        raise RunEvidenceValidationError(errors)


def monotonic_ms() -> int:
    return int(time.monotonic() * 1000)


def _dict_payload(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _object_payload(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        return dict(payload) if isinstance(payload, dict) else {}
    return {}


def _artifact_path(path: Path, artifact_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(artifact_root.resolve()))
    except ValueError:
        return str(path)


def _benchmark_sample_count(job: Any) -> int:
    sample_sizes = [
        int(metadata.get("sample_size", 0) or 0)
        for metadata in getattr(job, "suite_metadata", {}).values()
        if isinstance(metadata, dict)
    ]
    if sample_sizes:
        return sum(sample_sizes)
    return len(getattr(job, "suites", ())) * max(int(getattr(job, "repeats", 1) or 1), 1)


def _failure_summary(status: str, *, failure_count: int = 0) -> dict[str, object]:
    failed = status not in {"completed", "succeeded"}
    return {
        "failed": failed,
        "failure_count": failure_count if failure_count else int(failed),
        "status": status,
    }


def _fallback_summary(parameters: dict[str, str]) -> dict[str, object]:
    fallback_reason = str(parameters.get("fallback_reason", ""))
    fallback_count = int(bool(fallback_reason))
    return {
        "fallback_count": fallback_count,
        "fallbacks": [fallback_reason] if fallback_reason else [],
    }


def _run_started_at_monotonic_ms(
    *,
    artifact_write_started_at_monotonic_ms: int,
    duration_ms: int,
) -> int:
    return max(int(artifact_write_started_at_monotonic_ms) - max(int(duration_ms), 1), 0)


def _trace_id(run_id: str) -> str:
    return f"{run_id}:trace"


def _span_id(run_id: str, phase: str, suffix: str = "") -> str:
    safe_suffix = f":{suffix}" if suffix else ""
    return f"{run_id}:{phase}{safe_suffix}"


def _runtime_attributes(parameters: dict[str, str]) -> dict[str, object]:
    return {
        key: parameters[key]
        for key in _RUNTIME_ATTRIBUTE_KEYS
        if str(parameters.get(key, "")).strip()
    }


def _run_root_probe(
    *,
    run_id: str,
    trace_id: str,
    started_at_monotonic_ms: int,
    duration_ms: float,
) -> RunEvidenceProbe:
    return RunEvidenceProbe(
        run_id=run_id,
        trace_id=trace_id,
        span_id=_span_id(run_id, "worker_dispatch"),
        parent_span_id="",
        component="worker",
        phase="worker_dispatch",
        started_at_monotonic_ms=int(started_at_monotonic_ms),
        duration_ms=max(float(duration_ms), 0.001),
        status="completed",
        attributes={},
    )


def _runtime_prepare_probe(
    *,
    run_id: str,
    trace_id: str,
    parent_span_id: str,
    started_at_monotonic_ms: int,
    attributes: dict[str, object],
) -> RunEvidenceProbe:
    return _stage_probe(
        run_id=run_id,
        trace_id=trace_id,
        parent_span_id=parent_span_id,
        component="runtime",
        phase="runtime_prepare",
        started_at_monotonic_ms=started_at_monotonic_ms,
        duration_ms=0.001,
        status="completed",
        attributes=attributes,
    )


def _adapter_probe(
    *,
    run_id: str,
    trace_id: str,
    parent_span_id: str,
    started_at_monotonic_ms: int,
    adapter_id: str,
    adapter_snapshot: str,
) -> RunEvidenceProbe:
    loaded = bool(adapter_id.strip())
    return _stage_probe(
        run_id=run_id,
        trace_id=trace_id,
        parent_span_id=parent_span_id,
        component="adapter",
        phase="adapter_load",
        started_at_monotonic_ms=started_at_monotonic_ms,
        duration_ms=0.001,
        status="completed" if loaded else "skipped",
        attributes={"adapter_id": adapter_id, "adapter_snapshot": adapter_snapshot} if loaded else {},
    )


def _stage_probe(
    *,
    run_id: str,
    trace_id: str,
    parent_span_id: str,
    component: str,
    phase: str,
    started_at_monotonic_ms: int,
    duration_ms: float,
    status: str,
    attributes: dict[str, object],
    error_stage: str = "",
    error_code: str = "",
) -> RunEvidenceProbe:
    return RunEvidenceProbe(
        run_id=run_id,
        trace_id=trace_id,
        span_id=_span_id(run_id, phase, str(started_at_monotonic_ms)),
        parent_span_id=parent_span_id,
        component=component,
        phase=phase,
        started_at_monotonic_ms=int(started_at_monotonic_ms),
        duration_ms=max(float(duration_ms), 0.001),
        status=status,
        error_stage=error_stage,
        error_code=error_code,
        attributes=_small_attributes(attributes),
    )


def _benchmark_probe_attributes(*, row: dict[str, object], row_index: int) -> dict[str, object]:
    keys = (
        "job_id",
        "suite",
        "suite_id",
        "context_length",
        "generation_length",
        "batch_size",
        "repeat_index",
        "cell_id",
        "concurrency_level",
        "cache_profile",
        "reasoning_mode",
        "structured_output_mode",
        "runtime_kind",
        "runtime_name",
        "task_kind",
    )
    return {"row_index": row_index, **{key: row[key] for key in keys if key in row}}


def _evaluation_probe_attributes(*, payload: dict[str, object], sample_index: int) -> dict[str, object]:
    keys = (
        "job_id",
        "suite_id",
        "dataset_id",
        "sample_id",
        "task_kind",
        "extraction_status",
        "validation_status",
        "code_compile_status",
        "code_runtime_status",
        "code_timeout_status",
        "code_test_status",
        "category_label",
        "subject_label",
    )
    return {"sample_index": sample_index, **{key: payload[key] for key in keys if key in payload}}


def _evaluation_probe_failed(*, failure_stage: str, field_name: str, phase: str) -> bool:
    if not failure_stage:
        return False
    if failure_stage == phase or failure_stage == field_name.removesuffix("_ms"):
        return True
    return _EVALUATION_FAILURE_STAGE_PHASES.get(failure_stage) == phase


def _probe_summary_row(probe: RunEvidenceProbe) -> dict[str, object]:
    row: dict[str, object] = {
        "run_id": probe.run_id,
        "trace_id": probe.trace_id,
        "span_id": probe.span_id,
        "parent_span_id": probe.parent_span_id,
        "component": probe.component,
        "phase": probe.phase,
        "duration_ms": round(probe.duration_ms, 6),
        "status": probe.status,
        "error_stage": probe.error_stage,
        "error_code": probe.error_code,
    }
    if probe.attributes:
        row["attributes"] = dict(probe.attributes)
    return row


def _small_attributes(attributes: dict[str, object]) -> dict[str, object]:
    scrubbed: dict[str, object] = {}
    for key, value in attributes.items():
        if value in ("", None):
            continue
        if isinstance(value, (str, int, float, bool)):
            scrubbed[key] = value
        elif isinstance(value, (list, tuple)):
            scrubbed[key] = [item for item in value if isinstance(item, (str, int, float, bool))][:8]
        elif isinstance(value, dict):
            scrubbed[key] = {
                str(item_key): item_value
                for item_key, item_value in value.items()
                if isinstance(item_value, (str, int, float, bool))
            }
    return scrubbed


def _float_value(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _int_value(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _bool_value(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _git_output(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()
