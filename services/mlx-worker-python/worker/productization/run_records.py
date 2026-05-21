from __future__ import annotations

from functools import lru_cache
import json
import platform
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Mapping


RUN_RECORD_SCHEMA_VERSION = "melix.run_record.v1"

_SENSITIVE_KEY_RE = re.compile(
    r"(api[_-]?key|auth|bearer|credential|password|secret|token)",
    re.IGNORECASE,
)
_SENSITIVE_VALUE_RE = re.compile(
    r"^(sk-[A-Za-z0-9_\-]{8,}|Bearer\s+\S+|gh[pousr]_[A-Za-z0-9_]{8,})$",
    re.IGNORECASE,
)


def build_serving_benchmark_run_record(
    *,
    job: Any,
    results: tuple[Any, ...],
    artifact_root: Path,
    artifact_paths: Mapping[str, Path],
) -> dict[str, object]:
    parameters = _redacted_mapping(getattr(job, "parameters", {}))
    suites = list(getattr(job, "suites", ()))
    metrics = _benchmark_metrics(results)
    return _base_record(
        run_id=str(getattr(job, "job_id", "")),
        run_kind="benchmark",
        status=str(getattr(job, "status", "")),
        started_at_unix_ms=int(getattr(job, "created_at_unix_ms", 0) or 0),
        ended_at_unix_ms=int(getattr(job, "updated_at_unix_ms", 0) or 0),
        artifact_root=artifact_root,
        command=_command_payload(
            _serving_benchmark_argv(job=job, parameters=parameters),
            redacted=_has_redaction(parameters),
        ),
        target={
            "model_id": str(getattr(job, "model_id", "")),
            "task_kind": str(getattr(job, "task_kind", "")),
            "source_repo": str(getattr(job, "source_repo", "")),
            "runtime_backend": str(parameters.get("runtime_kind", "")),
        },
        dataset={
            "suite_ids": suites,
            "dataset_ref": str(parameters.get("dataset_ref", "")),
            "sample_size": _int_or_none(parameters.get("sample_size")),
            "batch_factor": _int_or_none(parameters.get("batch_factor")),
        },
        parameters=parameters,
        metrics=metrics,
        resources={
            "peak_memory_bytes": _max_metric_value(metrics, "peak_memory_bytes"),
            "estimated_active_memory_bytes": _int_or_none(
                parameters.get("memory_fit_estimated_active_memory_bytes")
            ),
            "estimated_disk_usage_bytes": _int_or_none(
                parameters.get("memory_fit_estimated_disk_usage_bytes")
            ),
        },
        artifacts=_artifact_entries(artifact_root=artifact_root, artifact_paths=artifact_paths),
        known_gaps=_known_gaps(parameters=parameters, telemetry_path=artifact_paths.get("telemetry_jsonl")),
    )


def build_benchmark_matrix_run_record(
    *,
    job: Any,
    summary_rows: tuple[Any, ...],
    artifact_root: Path,
    artifact_paths: Mapping[str, Path],
) -> dict[str, object]:
    parameters = _redacted_mapping(getattr(job, "parameters", {}))
    metrics = _benchmark_matrix_metrics(summary_rows)
    return _base_record(
        run_id=str(getattr(job, "job_id", "")),
        run_kind="benchmark_matrix",
        status=str(getattr(job, "status", "")),
        started_at_unix_ms=int(getattr(job, "created_at_unix_ms", 0) or 0),
        ended_at_unix_ms=int(getattr(job, "updated_at_unix_ms", 0) or 0),
        artifact_root=artifact_root,
        command=_command_payload(
            _benchmark_matrix_argv(job=job, summary_rows=summary_rows),
            redacted=_has_redaction(parameters),
        ),
        target={
            "model_id": str(getattr(job, "model_id", "")),
            "task_kind": str(getattr(job, "task_kind", "")),
            "source_repo": str(getattr(job, "source_repo", "")),
            "runtime_backend": str(parameters.get("runtime_kind", "")),
        },
        dataset={
            "suite_ids": list(getattr(job, "suite_ids", ())),
            "sample_size": _int_or_none(parameters.get("sample_size")),
            "batch_factor": _int_or_none(parameters.get("batch_factor")),
        },
        parameters=parameters,
        metrics=metrics,
        resources={"peak_memory_bytes": _max_metric_value(metrics, "peak_memory_bytes")},
        artifacts=_artifact_entries(artifact_root=artifact_root, artifact_paths=artifact_paths),
        known_gaps=_known_gaps(parameters=parameters, telemetry_path=artifact_paths.get("telemetry_jsonl")),
    )


def build_evaluation_run_record(
    *,
    job: Any,
    result: Any,
    artifact_root: Path,
    artifact_paths: Mapping[str, Path],
) -> dict[str, object]:
    parameters = _redacted_mapping(getattr(job, "parameters", {}))
    metrics = _metric_values(getattr(result, "metrics", ()))
    return _base_record(
        run_id=str(getattr(job, "job_id", "")),
        run_kind="evaluation",
        status=str(getattr(job, "status", "")),
        started_at_unix_ms=int(getattr(job, "created_at_unix_ms", 0) or 0),
        ended_at_unix_ms=int(getattr(job, "updated_at_unix_ms", 0) or 0),
        artifact_root=artifact_root,
        command=_command_payload(
            _evaluation_argv(job=job),
            redacted=_has_redaction(parameters),
        ),
        target={
            "model_id": str(getattr(job, "model_id", "")),
            "task_kind": str(getattr(job, "task_kind", "")),
            "source_repo": str(getattr(job, "source_repo", "")),
            "runtime_backend": str(parameters.get("runtime_kind", "")),
        },
        dataset={
            "suite_ids": [str(getattr(job, "suite_id", ""))],
            "dataset_id": str(getattr(job, "dataset_id", "")),
            "sample_size": int(getattr(job, "sample_size", 0) or 0),
            "scoring_mode": str(getattr(job, "scoring_mode", "")),
        },
        parameters=parameters,
        metrics=metrics,
        resources={"peak_memory_bytes": _int_or_none(parameters.get("peak_memory_bytes"))},
        artifacts=_artifact_entries(artifact_root=artifact_root, artifact_paths=artifact_paths),
        known_gaps=_known_gaps(parameters=parameters, telemetry_path=artifact_paths.get("telemetry_jsonl")),
        evaluation={
            "primary_score_name": str(getattr(result, "primary_score_name", "")),
            "primary_score_value": float(getattr(result, "primary_score_value", 0.0) or 0.0),
            "pass_count": int(getattr(result, "scored_sample_count", 0) or 0)
            - int(getattr(result, "failure_count", 0) or 0),
            "failure_count": int(getattr(result, "failure_count", 0) or 0),
            "duration_seconds": float(getattr(result, "duration_seconds", 0.0) or 0.0),
        },
    )


def build_evaluation_compare_run_record(
    *,
    job: Any,
    summaries: tuple[Any, ...],
    artifact_root: Path,
    artifact_paths: Mapping[str, Path],
) -> dict[str, object]:
    parameters = _redacted_mapping(getattr(job, "parameters", {}))
    metrics = _evaluation_compare_metrics(summaries)
    return _base_record(
        run_id=str(getattr(job, "job_id", "")),
        run_kind="evaluation_compare",
        status=str(getattr(job, "status", "")),
        started_at_unix_ms=int(getattr(job, "created_at_unix_ms", 0) or 0),
        ended_at_unix_ms=int(getattr(job, "updated_at_unix_ms", 0) or 0),
        artifact_root=artifact_root,
        command=_command_payload(
            _evaluation_compare_argv(job=job),
            redacted=_has_redaction(parameters),
        ),
        target={
            "base_model_id": str(getattr(job, "base_model_id", "")),
            "target_model_ids": list(getattr(job, "target_model_ids", ())),
            "target_lineage": _target_lineage(job),
            "task_kind": str(getattr(job, "task_kind", "")),
            "source_repo": str(getattr(job, "source_repo", "")),
            "runtime_backend": str(parameters.get("runtime_kind", "")),
        },
        dataset={
            "suite_ids": [str(getattr(job, "suite_id", ""))],
            "dataset_id": str(getattr(job, "dataset_id", "")),
            "sample_size": int(getattr(job, "sample_size", 0) or 0),
            "scoring_mode": str(getattr(job, "scoring_mode", "")),
            "dataset_lineage": _dataset_lineage(job),
        },
        parameters=parameters,
        metrics=metrics,
        resources={"peak_memory_bytes": _int_or_none(parameters.get("peak_memory_bytes"))},
        artifacts=_artifact_entries(artifact_root=artifact_root, artifact_paths=artifact_paths),
        known_gaps=_known_gaps(parameters=parameters, telemetry_path=artifact_paths.get("telemetry_jsonl")),
        evaluation={
            "win_count": sum(int(getattr(summary, "win_count", 0) or 0) for summary in summaries),
            "loss_count": sum(int(getattr(summary, "loss_count", 0) or 0) for summary in summaries),
            "tie_count": sum(int(getattr(summary, "tie_count", 0) or 0) for summary in summaries),
            "regression_count": sum(int(getattr(summary, "regression_count", 0) or 0) for summary in summaries),
            "verdicts": sorted({str(getattr(summary, "verdict", "")) for summary in summaries if str(getattr(summary, "verdict", ""))}),
            "statistical_verdicts": build_evaluation_compare_statistical_verdicts(summaries),
        },
    )


def attach_run_record_write_probe(record: dict[str, object], *, duration_ms: float) -> dict[str, object]:
    payload = dict(record)
    probes = list(payload.get("probes", [])) if isinstance(payload.get("probes"), list) else []
    probes.append(
        {
            "component": "worker.productization.run_records",
            "phase": "run_record_write",
            "duration_ms": round(float(duration_ms), 4),
            "status": "completed",
        }
    )
    payload["probes"] = probes
    return payload


def write_run_record(path: Path, record: Mapping[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(record), indent=2) + "\n", encoding="utf-8")
    return path


def _base_record(
    *,
    run_id: str,
    run_kind: str,
    status: str,
    started_at_unix_ms: int,
    ended_at_unix_ms: int,
    artifact_root: Path,
    command: dict[str, object],
    target: dict[str, object],
    dataset: dict[str, object],
    parameters: dict[str, object],
    metrics: list[dict[str, object]],
    resources: dict[str, object],
    artifacts: list[dict[str, object]],
    known_gaps: list[str],
    evaluation: dict[str, object] | None = None,
) -> dict[str, object]:
    record: dict[str, object] = {
        "schema_version": RUN_RECORD_SCHEMA_VERSION,
        "run_id": run_id,
        "run_kind": run_kind,
        "status": status,
        "started_at_unix_ms": started_at_unix_ms,
        "ended_at_unix_ms": ended_at_unix_ms,
        "duration_ms": max(0, ended_at_unix_ms - started_at_unix_ms),
        "command": command,
        "melix": _melix_identity(),
        "environment": _environment_summary(),
        "target": target,
        "dataset": dataset,
        "parameters": parameters,
        "reproducibility": _reproducibility(parameters),
        "metrics": metrics,
        "resources": resources,
        "artifact_root": str(artifact_root),
        "artifacts": artifacts,
        "known_gaps": known_gaps,
        "probes": [],
    }
    if evaluation is not None:
        record["evaluation"] = evaluation
    return record


def _command_payload(argv: list[str], *, redacted: bool) -> dict[str, object]:
    return {
        "argv": argv,
        "display": shlex.join(argv),
        "redacted": redacted,
    }


def _serving_benchmark_argv(*, job: Any, parameters: Mapping[str, object]) -> list[str]:
    argv = ["melix", "bench", "run"]
    _append_target(argv, model_id=str(getattr(job, "model_id", "")), source_repo=str(getattr(job, "source_repo", "")))
    for suite in getattr(job, "suites", ()):
        _append_option(argv, "--suite", suite)
    for context_length in getattr(job, "context_lengths", ()):
        _append_option(argv, "--context-length", context_length)
    _append_option(argv, "--generation-length", getattr(job, "generation_length", 0), skip_zero=True)
    for batch_size in getattr(job, "batch_sizes", ()):
        _append_option(argv, "--batch-size", batch_size)
    _append_option(argv, "--repeats", getattr(job, "repeats", 0), skip_zero=True)
    _append_option(argv, "--cache-profile", getattr(job, "cache_profile", ""))
    _append_option(argv, "--reasoning-mode", getattr(job, "reasoning_mode", ""))
    _append_option(argv, "--structured-output-mode", getattr(job, "structured_output_mode", ""))
    _append_option(argv, "--sample-size", parameters.get("sample_size"))
    _append_option(argv, "--batch-factor", parameters.get("batch_factor"))
    _append_option(argv, "--dataset-ref", parameters.get("dataset_ref"))
    return argv


def _benchmark_matrix_argv(*, job: Any, summary_rows: tuple[Any, ...]) -> list[str]:
    argv = ["melix", "bench", "matrix", "run"]
    _append_target(argv, model_id=str(getattr(job, "model_id", "")), source_repo=str(getattr(job, "source_repo", "")))
    _append_option(argv, "--task-kind", getattr(job, "task_kind", ""))
    for suite in getattr(job, "suite_ids", ()):
        _append_option(argv, "--suite", suite)
    parameters = getattr(job, "parameters", {})
    for key, option in (
        ("context_lengths", "--context-length"),
        ("generation_lengths", "--generation-length"),
        ("batch_sizes", "--batch-size"),
        ("cache_profiles", "--cache-profile"),
        ("reasoning_modes", "--reasoning-mode"),
        ("structured_output_modes", "--structured-output-mode"),
        ("concurrency_levels", "--concurrency"),
    ):
        values = _split_parameter_list(parameters.get(key, ""))
        if not values:
            values = _matrix_values_from_rows(summary_rows, key)
        for value in values:
            _append_option(argv, option, value)
    _append_option(argv, "--repeats", parameters.get("repeats") or _first_matrix_value(summary_rows, "repeats"))
    _append_option(argv, "--requests", parameters.get("requests") or _first_matrix_value(summary_rows, "requests"))
    _append_option(
        argv,
        "--duration-seconds",
        parameters.get("duration_seconds") or _first_matrix_value(summary_rows, "duration_seconds"),
    )
    return argv


def _evaluation_argv(*, job: Any) -> list[str]:
    argv = ["melix", "eval", "run"]
    _append_target(argv, model_id=str(getattr(job, "model_id", "")), source_repo=str(getattr(job, "source_repo", "")))
    _append_option(argv, "--suite", getattr(job, "suite_id", ""))
    _append_option(argv, "--dataset-id", getattr(job, "dataset_id", ""))
    _append_option(argv, "--sample-size", getattr(job, "sample_size", 0))
    parameters = getattr(job, "parameters", {})
    _append_option(argv, "--scoring-mode", getattr(job, "scoring_mode", ""))
    _append_option(argv, "--few-shot", getattr(job, "few_shot", 0))
    _append_option(argv, "--seed", getattr(job, "seed", 0))
    _append_option(argv, "--code-exec-policy", getattr(job, "code_exec_policy", ""))
    _append_option(argv, "--dataset-ref", parameters.get("dataset_ref", ""))
    return argv


def _evaluation_compare_argv(*, job: Any) -> list[str]:
    argv = ["melix", "eval", "compare"]
    _append_option(argv, "--base-model-id", getattr(job, "base_model_id", ""))
    for target_model_id in getattr(job, "target_model_ids", ()):
        _append_option(argv, "--target-model-id", target_model_id)
    _append_option(argv, "--suite", getattr(job, "suite_id", ""))
    _append_option(argv, "--dataset-id", getattr(job, "dataset_id", ""))
    _append_option(argv, "--sample-size", getattr(job, "sample_size", 0))
    return argv


def _append_target(argv: list[str], *, model_id: str, source_repo: str) -> None:
    if model_id:
        _append_option(argv, "--model-id", model_id)
    elif source_repo and not source_repo.startswith("remote:"):
        _append_option(argv, "--repo-id", source_repo)


def _append_option(argv: list[str], option: str, value: object, *, skip_zero: bool = False) -> None:
    if value is None:
        return
    string_value = str(value).strip()
    if not string_value:
        return
    if skip_zero and string_value == "0":
        return
    argv.extend([option, string_value])


def _split_parameter_list(value: object) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def _matrix_values_from_rows(summary_rows: tuple[Any, ...], key: str) -> list[str]:
    field_by_key = {
        "context_lengths": "context_length",
        "generation_lengths": "generation_length",
        "batch_sizes": "batch_size",
        "cache_profiles": "cache_profile",
        "reasoning_modes": "reasoning_mode",
        "structured_output_modes": "structured_output_mode",
        "concurrency_levels": "concurrency_level",
    }
    field = field_by_key.get(key, "")
    if not field:
        return []
    values = {
        str(getattr(row, field, "")).strip()
        for row in summary_rows
        if str(getattr(row, field, "")).strip()
    }
    return sorted(values)


def _first_matrix_value(summary_rows: tuple[Any, ...], field: str) -> object:
    for row in summary_rows:
        value = getattr(row, field, None)
        if value not in (None, "", 0):
            return value
    return ""


def _benchmark_metrics(results: tuple[Any, ...]) -> list[dict[str, object]]:
    metrics: list[dict[str, object]] = []
    seen: set[str] = set()
    for result in results:
        for metric in getattr(result, "metrics", ()):
            payload = _metric_payload(metric)
            key = str(payload["name"])
            if key in seen:
                continue
            seen.add(key)
            metrics.append(payload)
    return metrics


def _benchmark_matrix_metrics(summary_rows: tuple[Any, ...]) -> list[dict[str, object]]:
    aggregates: dict[str, list[float]] = {}
    for row in summary_rows:
        for key in (
            "ttft_mean_ms",
            "request_latency_mean_ms",
            "prefill_tokens_per_second_mean",
            "decode_tokens_per_second_mean",
            "throughput_requests_per_second",
            "throughput_tokens_per_second",
            "success_rate",
            "peak_memory_bytes_max",
            "queue_wait_mean_ms",
            "queue_wait_p95_ms",
        ):
            value = _float_or_none(getattr(row, key, None))
            if value is not None:
                aggregates.setdefault(f"benchmark_matrix.{key}", []).append(value)
    metrics: list[dict[str, object]] = []
    for name, values in sorted(aggregates.items()):
        metrics.append(
            {
                "name": name,
                "value": round(sum(values) / max(len(values), 1), 4),
                "unit": _unit_for_metric(name),
            }
        )
    return metrics


def _evaluation_compare_metrics(summaries: tuple[Any, ...]) -> list[dict[str, object]]:
    metrics: list[dict[str, object]] = []
    for summary in summaries:
        target_model_id = str(getattr(summary, "target_model_id", "target"))
        for metric in getattr(summary, "metrics", ()):
            payload = _metric_payload(metric)
            payload["name"] = f"{target_model_id}.{payload['name']}"
            metrics.append(payload)
    return metrics


def _dataset_lineage(job: Any) -> dict[str, object]:
    return object_payload(getattr(job, "dataset_lineage", None))


def _target_lineage(job: Any) -> list[dict[str, object]]:
    lineage: list[dict[str, object]] = []
    for entry in getattr(job, "target_lineage", ()):
        payload = object_payload(entry)
        if payload:
            lineage.append(payload)
    return lineage


def build_evaluation_compare_statistical_verdicts(summaries: tuple[Any, ...]) -> list[dict[str, object]]:
    verdicts: list[dict[str, object]] = []
    for summary in summaries:
        verdicts.append(build_evaluation_compare_statistical_verdict(summary))
    return verdicts


def build_evaluation_compare_statistical_verdict(summary: Any) -> dict[str, object]:
    return {
        "target_model_id": str(getattr(summary, "target_model_id", "")),
        "verdict": str(getattr(summary, "verdict", "")),
        "effect_threshold": float(getattr(summary, "effect_threshold", 0.0) or 0.0),
        "delta_accuracy": float(getattr(summary, "delta_accuracy", 0.0) or 0.0),
        "base_accuracy": float(getattr(summary, "base_accuracy", 0.0) or 0.0),
        "target_accuracy": float(getattr(summary, "target_accuracy", 0.0) or 0.0),
        "win_count": int(getattr(summary, "win_count", 0) or 0),
        "loss_count": int(getattr(summary, "loss_count", 0) or 0),
        "tie_count": int(getattr(summary, "tie_count", 0) or 0),
        "regression_count": int(getattr(summary, "regression_count", 0) or 0),
        "statistical_evidence": object_payload(getattr(summary, "statistical_evidence", {})),
        "release_gate_summary": object_payload(getattr(summary, "release_gate_summary", {})),
    }


def object_payload(value: object) -> dict[str, object]:
    if value is None:
        return {}
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return dict(payload)
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _metric_values(metrics: tuple[Any, ...]) -> list[dict[str, object]]:
    return [_metric_payload(metric) for metric in metrics]


def _metric_payload(metric: Any) -> dict[str, object]:
    return {
        "name": str(getattr(metric, "name", "")),
        "value": float(getattr(metric, "value", 0.0) or 0.0),
        "unit": str(getattr(metric, "unit", "")),
    }


def _unit_for_metric(name: str) -> str:
    if name.endswith("_ms") or "_ms_" in name:
        return "ms"
    if "tokens_per_second" in name or "requests_per_second" in name:
        return "/s"
    if name.endswith("_bytes") or "_bytes_" in name:
        return "bytes"
    return ""


def _max_metric_value(metrics: list[dict[str, object]], fragment: str) -> int | None:
    values = [
        _float_or_none(metric.get("value"))
        for metric in metrics
        if fragment in str(metric.get("name", ""))
    ]
    values = [value for value in values if value is not None]
    if not values:
        return None
    return int(max(values))


def _artifact_entries(*, artifact_root: Path, artifact_paths: Mapping[str, Path]) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for kind, path in sorted(artifact_paths.items()):
        path_obj = Path(path)
        try:
            relative_path = str(path_obj.relative_to(artifact_root))
        except ValueError:
            relative_path = ""
        entries.append(
            {
                "kind": kind,
                "path": str(path_obj),
                "relative_path": relative_path,
            }
        )
    return entries


def _redacted_mapping(parameters: Mapping[str, object]) -> dict[str, object]:
    redacted: dict[str, object] = {}
    for key, value in sorted(parameters.items()):
        key_text = str(key)
        redacted[key_text] = _redacted_value(key_text, value)
    return redacted


def _redacted_value(key: str, value: object) -> object:
    if _is_sensitive(key, value):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(child_key): _redacted_value(str(child_key), child_value) for child_key, child_value in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redacted_value(key, child_value) for child_value in value]
    return value


def _is_sensitive(key: str, value: object) -> bool:
    if _SENSITIVE_KEY_RE.search(key):
        return True
    if isinstance(value, str) and _SENSITIVE_VALUE_RE.match(value.strip()):
        return True
    return False


def _has_redaction(parameters: Mapping[str, object]) -> bool:
    return any(_contains_redaction(value) for value in parameters.values())


def _contains_redaction(value: object) -> bool:
    if str(value) == "[REDACTED]":
        return True
    if isinstance(value, Mapping):
        return any(_contains_redaction(child_value) for child_value in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_redaction(child_value) for child_value in value)
    return False


def _reproducibility(parameters: Mapping[str, object]) -> dict[str, object]:
    keys = (
        "schema_sha256",
        "schema_size_bytes",
        "hints_sha256",
        "hints_size_bytes",
        "hints_format",
        "prompt_template_digest",
        "input_digest",
    )
    return {key: parameters[key] for key in keys if parameters.get(key) not in (None, "")}


def _known_gaps(*, parameters: Mapping[str, object], telemetry_path: Path | None) -> list[str]:
    gaps: list[str] = []
    if telemetry_path is None or not str(telemetry_path):
        gaps.append("Apple Silicon telemetry artifact was not present for this run.")
    if _has_redaction(parameters):
        gaps.append("Sensitive command or request values were redacted from the persisted run record.")
    return gaps


def _environment_summary() -> dict[str, object]:
    mac_version = platform.mac_ver()[0]
    return {
        "platform": platform.system() or "unknown",
        "macos_version": mac_version,
        "machine": platform.machine(),
        "processor": _apple_processor_name(),
    }


@lru_cache(maxsize=1)
def _apple_processor_name() -> str:
    try:
        completed = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except Exception:
        return platform.processor()
    value = completed.stdout.strip()
    return value or platform.processor()


@lru_cache(maxsize=1)
def _melix_identity() -> dict[str, object]:
    repo_root = _repo_root()
    return {
        "git_commit": _git_output(repo_root, "rev-parse", "HEAD"),
        "git_branch": _git_output(repo_root, "rev-parse", "--abbrev-ref", "HEAD"),
        "dirty_worktree": _git_dirty(repo_root),
        "version": "",
    }


def _repo_root(start: Path | None = None) -> Path:
    start_path = (start or Path(__file__)).resolve()
    cursor = start_path if start_path.is_dir() else start_path.parent
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cursor,
            check=False,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except Exception:
        completed = None
    if completed is not None and completed.returncode == 0:
        path = completed.stdout.strip()
        if path:
            return Path(path)
    for candidate in (cursor, *cursor.parents):
        if (candidate / ".git").exists() or (candidate / "AGENTS.md").exists():
            return candidate
    return Path(__file__).resolve().parents[4]


def _git_output(repo_root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except Exception:
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _git_dirty(repo_root: Path) -> bool:
    try:
        completed = subprocess.run(
            ["git", "status", "--short"],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except Exception:
        return False
    return bool(completed.stdout.strip()) if completed.returncode == 0 else False


def _int_or_none(value: object) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _float_or_none(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
