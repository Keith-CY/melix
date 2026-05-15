from __future__ import annotations

import json
import math
import threading
import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any


SERVING_DIAGNOSTICS_MANIFEST_SCHEMA_VERSION = "melix.serving_diagnostics.manifest.v1"
SERVING_DIAGNOSTICS_REQUEST_SCHEMA_VERSION = "melix.serving_diagnostics.request_summary.v1"
SERVING_DIAGNOSTICS_EVENT_SCHEMA_VERSION = "melix.serving_diagnostics.event.v1"
SERVING_DIAGNOSTICS_COMPARISON_SCHEMA_VERSION = "melix.serving_diagnostics.comparison.v1"
_EMPTY_EVENT_ATTRIBUTES: Mapping[str, object] = MappingProxyType({})
_JSON_COMPACT_SEPARATORS = (",", ":")
_JSONL_ENCODER = json.JSONEncoder(sort_keys=True, separators=_JSON_COMPACT_SEPARATORS)
_JSON_STRING_ENCODER = json.JSONEncoder(separators=_JSON_COMPACT_SEPARATORS).encode
_SET_FROZEN_ATTR = object.__setattr__


class ServingDiagnosticsComparisonError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ServingDiagnosticsQueueSnapshot:
    events: tuple[ServingDiagnosticsEvent, ...]
    dropped_count: int


class BoundedServingDiagnosticsEventQueue:
    __slots__ = (
        "_dropped_count",
        "_events",
        "_is_saturated",
        "_lock",
        "_max_events",
        "_retained_count",
    )

    def __init__(self, *, max_events: int = 256) -> None:
        self._max_events = max(int(max_events), 1)
        self._events: deque[ServingDiagnosticsEvent] = deque(maxlen=self._max_events)
        self._dropped_count = 0
        self._is_saturated = False
        self._retained_count = 0
        self._lock = threading.Lock()

    def append(self, event: ServingDiagnosticsEvent) -> bool:
        lock = self._lock
        lock.acquire()
        try:
            events = self._events
            if self._is_saturated:
                self._dropped_count += 1
                events.append(event)
                return False
            events.append(event)
            retained_count = self._retained_count + 1
            self._retained_count = retained_count
            self._is_saturated = retained_count >= self._max_events
            return True
        finally:
            lock.release()

    def snapshot(self) -> ServingDiagnosticsQueueSnapshot:
        with self._lock:
            return ServingDiagnosticsQueueSnapshot(
                events=tuple(self._events),
                dropped_count=self._dropped_count,
            )


@dataclass(frozen=True, slots=True)
class ServingDiagnosticsRequestSummary:
    request_id: str
    task_kind: str
    model_id: str
    runtime_kind: str
    acceleration_mode: str
    prompt_protocol_id: str
    prompt_digest: str
    prompt_template_digest: str
    generation_config: dict[str, object]
    status: str
    finish_reason: str
    started_at_unix_ms: int = 0
    ended_at_unix_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    prefill_chunk_size: int = 0
    prefill_ms: float = 0.0
    decode_ms: float = 0.0
    prompt_tps: float = 0.0
    generation_tps: float = 0.0
    prefill_tokens_per_second: float = 0.0
    cache_hit_tokens: int = 0
    cache_miss_tokens: int = 0
    cache_restored_tokens: int = 0
    cache_computed_tokens: int = 0
    memory_used_bytes: int = 0
    memory_total_bytes: int = 0
    peak_memory_bytes: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SERVING_DIAGNOSTICS_REQUEST_SCHEMA_VERSION,
            "request_id": self.request_id,
            "task_kind": self.task_kind,
            "model_id": self.model_id,
            "runtime_kind": self.runtime_kind,
            "acceleration_mode": self.acceleration_mode,
            "prompt_protocol_id": self.prompt_protocol_id,
            "prompt_digest": self.prompt_digest,
            "prompt_template_digest": self.prompt_template_digest,
            "generation_config": dict(self.generation_config),
            "status": self.status,
            "finish_reason": self.finish_reason,
            "started_at_unix_ms": int(self.started_at_unix_ms),
            "ended_at_unix_ms": int(self.ended_at_unix_ms),
            "prompt_tokens": int(self.prompt_tokens),
            "completion_tokens": int(self.completion_tokens),
            "prefill_chunk_size": int(self.prefill_chunk_size),
            "prefill_ms": float(self.prefill_ms),
            "decode_ms": float(self.decode_ms),
            "prompt_tps": float(self.prompt_tps),
            "generation_tps": float(self.generation_tps),
            "prefill_tokens_per_second": float(self.prefill_tokens_per_second),
            "cache_hit_tokens": int(self.cache_hit_tokens),
            "cache_miss_tokens": int(self.cache_miss_tokens),
            "cache_restored_tokens": int(self.cache_restored_tokens),
            "cache_computed_tokens": int(self.cache_computed_tokens),
            "memory_used_bytes": int(self.memory_used_bytes),
            "memory_total_bytes": int(self.memory_total_bytes),
            "peak_memory_bytes": int(self.peak_memory_bytes),
        }


@dataclass(frozen=True, slots=True, init=False)
class ServingDiagnosticsEvent:
    request_id: str
    phase: str
    event_index: int
    status: str
    duration_ms: float = 0.0
    attributes: Mapping[str, object] = _EMPTY_EVENT_ATTRIBUTES

    def __init__(
        self,
        request_id: str,
        phase: str,
        event_index: int,
        status: str,
        duration_ms: float = 0.0,
        attributes: Mapping[str, object] = _EMPTY_EVENT_ATTRIBUTES,
    ) -> None:
        set_attr = _SET_FROZEN_ATTR
        set_attr(self, "request_id", request_id)
        set_attr(self, "phase", phase)
        set_attr(self, "event_index", event_index)
        set_attr(self, "status", status)
        set_attr(self, "duration_ms", duration_ms)
        set_attr(self, "attributes", attributes)

    def to_dict(self) -> dict[str, object]:
        attributes = self.attributes
        event_index = self.event_index
        duration_ms = self.duration_ms
        return {
            "schema_version": SERVING_DIAGNOSTICS_EVENT_SCHEMA_VERSION,
            "request_id": self.request_id,
            "phase": self.phase,
            "event_index": event_index
            if type(event_index) is int
            else int(event_index),
            "status": self.status,
            "duration_ms": duration_ms
            if type(duration_ms) is float
            else float(duration_ms),
            "attributes": {}
            if attributes is _EMPTY_EVENT_ATTRIBUTES
            else _stable_json_object(attributes),
        }


@dataclass(frozen=True)
class ServingEvidenceRun:
    run_id: str
    model_id: str
    task_kind: str
    prompt_protocol_id: str
    prompt_digest: str
    prompt_template_digest: str
    generation_config: dict[str, object]
    acceleration_mode: str
    acceleration_admitted: bool
    fallback_reason: str
    effective_temperature: float
    effective_top_p: float
    effective_top_k: int
    tier_stability_status: str
    metrics: dict[str, float]

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "model_id": self.model_id,
            "task_kind": self.task_kind,
            "prompt_protocol_id": self.prompt_protocol_id,
            "prompt_digest": self.prompt_digest,
            "prompt_template_digest": self.prompt_template_digest,
            "generation_config": dict(self.generation_config),
            "acceleration_mode": self.acceleration_mode,
            "acceleration_admitted": bool(self.acceleration_admitted),
            "fallback_reason": self.fallback_reason,
            "effective_temperature": float(self.effective_temperature),
            "effective_top_p": float(self.effective_top_p),
            "effective_top_k": int(self.effective_top_k),
            "sampler_is_greedy": self.sampler_is_greedy,
            "tier_stability_status": self.tier_stability_status,
            "metrics": {
                str(key): float(value)
                for key, value in sorted(self.metrics.items())
            },
        }

    @property
    def sampler_is_greedy(self) -> bool:
        return (
            float(self.effective_temperature) == 0.0
            and float(self.effective_top_p) == 1.0
            and int(self.effective_top_k) in {0, 1}
        )


def validate_prefill_chunk_size(value: object) -> int:
    try:
        chunk_size = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError("prefill_chunk_size must be a positive integer") from exc
    if chunk_size <= 0:
        raise ValueError("prefill_chunk_size must be a positive integer")
    return chunk_size


def write_serving_diagnostics_bundle(
    *,
    output_root: Path,
    bundle_id: str,
    invocation: dict[str, object],
    effective_config: dict[str, object],
    model_refs: dict[str, object],
    request_summary: ServingDiagnosticsRequestSummary,
    events: tuple[ServingDiagnosticsEvent, ...] | ServingDiagnosticsQueueSnapshot,
    diagnostics_mode: str,
) -> dict[str, Path]:
    if request_summary.prefill_chunk_size:
        validate_prefill_chunk_size(request_summary.prefill_chunk_size)
    if diagnostics_mode not in {"debug", "claim_evidence"}:
        raise ValueError("diagnostics_mode must be debug or claim_evidence")

    bundle_root = output_root / "serving-diagnostics" / _safe_artifact_id(bundle_id)
    bundle_root.mkdir(parents=True, exist_ok=True)
    manifest_path = bundle_root / "manifest.json"
    effective_config_path = bundle_root / "effective-config.json"
    request_summary_path = bundle_root / "request-summary.json"
    events_path = bundle_root / "events.jsonl"

    event_rows, dropped_event_count = _event_rows_and_dropped_count(events)
    manifest = {
        "schema_version": SERVING_DIAGNOSTICS_MANIFEST_SCHEMA_VERSION,
        "bundle_id": bundle_id,
        "created_at_unix_ms": int(time.time() * 1000),
        "diagnostics_mode": diagnostics_mode,
        "public_performance_claim_eligible": diagnostics_mode == "claim_evidence",
        "invocation": _stable_json_object(invocation),
        "model_refs": _stable_json_object(model_refs),
        "request_id": request_summary.request_id,
        "task_kind": request_summary.task_kind,
        "model_id": request_summary.model_id,
        "runtime_kind": request_summary.runtime_kind,
        "acceleration_mode": request_summary.acceleration_mode,
        "event_count": len(event_rows),
        "dropped_event_count": dropped_event_count,
        "artifacts": {
            "effective_config": "effective-config.json",
            "request_summary": "request-summary.json",
            "events": "events.jsonl",
        },
    }

    _write_json(manifest_path, manifest)
    _write_json(effective_config_path, _stable_json_object(effective_config))
    _write_json(request_summary_path, request_summary.to_dict())
    _write_jsonl(events_path, event_rows)
    return {
        "bundle_root": bundle_root,
        "manifest": manifest_path,
        "effective_config": effective_config_path,
        "request_summary": request_summary_path,
        "events": events_path,
    }


def write_baseline_accelerated_evidence(
    *,
    output_root: Path,
    comparison_id: str,
    baseline: ServingEvidenceRun,
    accelerated: ServingEvidenceRun,
) -> dict[str, Path]:
    _validate_comparable_runs(baseline, accelerated)
    phase_rows = _comparison_phase_rows(baseline, accelerated)

    comparison_root = output_root / "serving-diagnostics" / _safe_artifact_id(comparison_id)
    comparison_root.mkdir(parents=True, exist_ok=True)
    comparison_path = comparison_root / "baseline-vs-accelerated.json"
    payload = {
        "schema_version": SERVING_DIAGNOSTICS_COMPARISON_SCHEMA_VERSION,
        "comparison_id": comparison_id,
        "created_at_unix_ms": int(time.time() * 1000),
        "comparison_validity": "valid",
        "methodology": _comparison_methodology(baseline, accelerated),
        "runs": {
            "baseline": baseline.to_dict(),
            "accelerated": accelerated.to_dict(),
        },
        "phase_rows": phase_rows,
    }
    _write_json(comparison_path, payload)
    return {
        "comparison_root": comparison_root,
        "comparison": comparison_path,
    }


def _validate_comparable_runs(
    baseline: ServingEvidenceRun,
    accelerated: ServingEvidenceRun,
) -> None:
    for field_name in (
        "prompt_protocol_id",
        "prompt_digest",
        "prompt_template_digest",
        "model_id",
        "task_kind",
    ):
        if getattr(baseline, field_name) != getattr(accelerated, field_name):
            raise ServingDiagnosticsComparisonError(
                f"{field_name} must match for baseline-vs-accelerated evidence"
            )
    if dict(baseline.generation_config) != dict(accelerated.generation_config):
        raise ServingDiagnosticsComparisonError(
            "generation_config must match for baseline-vs-accelerated evidence"
        )
    if not baseline.sampler_is_greedy or not accelerated.sampler_is_greedy:
        raise ServingDiagnosticsComparisonError(
            "baseline-vs-accelerated evidence requires greedy deterministic sampling"
        )
    if baseline.tier_stability_status != accelerated.tier_stability_status:
        raise ServingDiagnosticsComparisonError(
            "tier_stability_status must match for baseline-vs-accelerated evidence"
        )


def _comparison_methodology(
    baseline: ServingEvidenceRun,
    accelerated: ServingEvidenceRun,
) -> dict[str, object]:
    return {
        "prompt_protocol_id": baseline.prompt_protocol_id,
        "prompt_digest": baseline.prompt_digest,
        "model_id": baseline.model_id,
        "task_kind": baseline.task_kind,
        "effective_temperature": float(accelerated.effective_temperature),
        "effective_top_p": float(accelerated.effective_top_p),
        "effective_top_k": int(accelerated.effective_top_k),
        "sampler_is_greedy": accelerated.sampler_is_greedy,
        "tier_stability_status": accelerated.tier_stability_status,
    }


def _comparison_phase_rows(
    baseline: ServingEvidenceRun,
    accelerated: ServingEvidenceRun,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for phase, metric_name in (
        ("prefill", "prefill_ms"),
        ("decode", "decode_ms"),
    ):
        baseline_value = _required_metric_value(baseline, metric_name)
        accelerated_value = _required_metric_value(accelerated, metric_name)
        rows.append(
            {
                "phase": phase,
                "metric": metric_name,
                "unit": "ms",
                "baseline": baseline_value,
                "accelerated": accelerated_value,
                "delta": round(accelerated_value - baseline_value, 6),
                "direction": "lower_is_better",
            }
        )
    return rows


def _event_rows_and_dropped_count(
    events: tuple[ServingDiagnosticsEvent, ...] | ServingDiagnosticsQueueSnapshot,
) -> tuple[tuple[ServingDiagnosticsEvent, ...], int]:
    if isinstance(events, ServingDiagnosticsQueueSnapshot):
        return events.events, events.dropped_count
    return events, 0


def _required_metric_value(run: ServingEvidenceRun, metric_name: str) -> float:
    if metric_name not in run.metrics:
        raise ServingDiagnosticsComparisonError(
            f"{metric_name} is required for baseline-vs-accelerated evidence"
        )
    try:
        metric_value = float(run.metrics[metric_name])
    except (TypeError, ValueError) as exc:
        raise ServingDiagnosticsComparisonError(
            f"{metric_name} must be a finite number for baseline-vs-accelerated evidence"
        ) from exc
    if not math.isfinite(metric_value):
        raise ServingDiagnosticsComparisonError(
            f"{metric_name} must be a finite number for baseline-vs-accelerated evidence"
        )
    return metric_value


def _safe_artifact_id(value: str) -> str:
    stripped = value.strip()
    if not stripped or stripped in {".", ".."} or "/" in stripped or "\x00" in stripped:
        raise ValueError("artifact id must be non-empty and path-local")
    return stripped


def _stable_json_object(payload: Mapping[str, object]) -> dict[str, object]:
    return {
        str(key): _stable_json_value(value)
        for key, value in sorted(payload.items(), key=lambda item: str(item[0]))
    }


def _stable_json_value(value: object) -> object:
    if isinstance(value, dict):
        return _stable_json_object(value)  # type: ignore[arg-type]
    if isinstance(value, (list, tuple)):
        return [_stable_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [
            _stable_json_value(item)
            for item in sorted(value, key=_stable_json_sort_key)
        ]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _stable_json_sort_key(value: object) -> str:
    return json.dumps(_stable_json_value(value), sort_keys=True, separators=(",", ":"))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: Any) -> None:
    with path.open("w", encoding="utf-8") as handle:
        encode = _JSONL_ENCODER.encode
        write = handle.write
        for row in rows:
            if isinstance(row, ServingDiagnosticsEvent):
                fast_line = _empty_attribute_event_json_line(row)
                if fast_line is not None:
                    write(fast_line + "\n")
                    continue
                row = row.to_dict()
            write(encode(row) + "\n")


def _empty_attribute_event_json_line(event: ServingDiagnosticsEvent) -> str | None:
    if event.attributes is not _EMPTY_EVENT_ATTRIBUTES:
        return None
    event_index = event.event_index
    duration_ms = event.duration_ms
    if type(event_index) is not int or type(duration_ms) is not float:
        return None
    if not math.isfinite(duration_ms):
        return None
    encode_string = _JSON_STRING_ENCODER
    return (
        '{"attributes":{},"duration_ms":'
        f"{duration_ms!r}"
        ',"event_index":'
        f"{event_index}"
        ',"phase":'
        f"{encode_string(event.phase)}"
        ',"request_id":'
        f"{encode_string(event.request_id)}"
        ',"schema_version":"melix.serving_diagnostics.event.v1","status":'
        f"{encode_string(event.status)}"
        "}"
    )
