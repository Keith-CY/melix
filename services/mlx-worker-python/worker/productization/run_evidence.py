from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


RUN_EVIDENCE_SCHEMA_VERSION = "melix.run_evidence.v1"
TELEMETRY_SUMMARY_SCHEMA_VERSION = "melix.telemetry_summary.v1"


class RunEvidenceValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = tuple(errors)
        super().__init__("; ".join(errors))


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

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": TELEMETRY_SUMMARY_SCHEMA_VERSION,
            "collector_status": self.collector_status,
            "time_series_path": self.time_series_path,
            "telemetry_failures": list(self.telemetry_failures),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> RunEvidenceTelemetrySummary:
        failures = payload.get("telemetry_failures")
        return cls(
            collector_status=str(payload.get("collector_status") or ""),
            time_series_path=str(payload.get("time_series_path") or ""),
            telemetry_failures=tuple(str(item) for item in failures) if isinstance(failures, list) else (),
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
        collector_status="not_collected",
        telemetry_failures=(
            "apple_silicon_telemetry_collector_not_connected_until_milestone_3",
        ),
    )


def build_serving_benchmark_run_evidence(
    *,
    job: Any,
    results: tuple[Any, ...],
    artifact_root: Path,
    artifact_paths: dict[str, Path],
    artifact_write_started_at_monotonic_ms: int,
    artifact_write_duration_ms: float,
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
        probe_timeline=(
            artifact_write_probe(
                run_id=job.job_id,
                started_at_monotonic_ms=artifact_write_started_at_monotonic_ms,
                duration_ms=artifact_write_duration_ms,
                artifact_count=len(artifacts),
            ),
        ),
        telemetry_summary=default_telemetry_summary(),
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
        probe_timeline=(
            artifact_write_probe(
                run_id=job.job_id,
                started_at_monotonic_ms=artifact_write_started_at_monotonic_ms,
                duration_ms=artifact_write_duration_ms,
                artifact_count=len(artifacts),
            ),
        ),
        telemetry_summary=default_telemetry_summary(),
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


def artifact_write_probe(
    *,
    run_id: str,
    started_at_monotonic_ms: int,
    duration_ms: float,
    artifact_count: int,
) -> RunEvidenceProbe:
    return RunEvidenceProbe(
        run_id=run_id,
        trace_id=f"{run_id}:trace",
        span_id=f"{run_id}:artifact_write",
        parent_span_id="",
        component="report",
        phase="artifact_write",
        started_at_monotonic_ms=started_at_monotonic_ms,
        duration_ms=max(duration_ms, 0.001),
        status="completed",
        attributes={"artifact_count": artifact_count},
    )


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


def _git_output(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()
