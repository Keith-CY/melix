from __future__ import annotations

import json
import math
import threading
import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any

from worker.productization.privacy_policy_receipts import (
    _bool_value,
    network_fetch_policy_receipt_from_metadata,
    privacy_audit_counter_from_metadata,
    privacy_detector_receipt_from_metadata,
)


SERVING_DIAGNOSTICS_MANIFEST_SCHEMA_VERSION = "melix.serving_diagnostics.manifest.v1"
SERVING_DIAGNOSTICS_REQUEST_SCHEMA_VERSION = "melix.serving_diagnostics.request_summary.v1"
SERVING_DIAGNOSTICS_EVENT_SCHEMA_VERSION = "melix.serving_diagnostics.event.v1"
SERVING_DIAGNOSTICS_COMPARISON_SCHEMA_VERSION = "melix.serving_diagnostics.comparison.v1"
_PROFILE_AUDIT_TO_RECEIPT_FIELDS = {
    "melix.acceleration.profile.requested_profile": "requested_profile",
    "melix.acceleration.profile.effective_profile": "effective_profile",
    "melix.acceleration.profile.profile_mode": "profile_mode",
    "melix.acceleration.profile.proof_matrix_id": "proof_matrix_id",
    "melix.acceleration.profile.verification_status": "verification_status",
    "melix.acceleration.profile.profile_admission_status": "profile_admission_status",
    "melix.acceleration.profile.fallback_reason": "fallback_reason",
    "melix.acceleration.profile.recovery_hint": "recovery_hint",
}
_PROFILE_RECEIPT_REQUIRED_FIELDS = frozenset(
    ("requested_profile", "effective_profile", "profile_admission_status")
)
_READINESS_AUDIT_TO_RECEIPT_FIELDS = {
    "melix.serving.readiness.requested_model_id": "requested_model_id",
    "melix.serving.readiness.effective_model_id": "effective_model_id",
    "melix.serving.readiness.identity_source": "identity_source",
    "melix.serving.readiness.budget_source": "budget_source",
    "melix.serving.readiness.health_ready_at": "health_ready_at",
    "melix.serving.readiness.progress_source": "progress_source",
    "melix.serving.readiness.dependency_policy_status": "dependency_policy_status",
}
_READINESS_RECEIPT_REQUIRED_FIELDS = frozenset(
    _READINESS_AUDIT_TO_RECEIPT_FIELDS.values()
)
_CAPABILITY_AUDIT_TO_RECEIPT_FIELDS = {
    "melix.serving.capability.schema_version": "schema_version",
    "melix.serving.capability.capabilities": "capabilities",
    "melix.serving.capability.input_modalities": "input_modalities",
    "melix.serving.capability.output_modalities": "output_modalities",
    "melix.serving.capability.acceleration_profile": "acceleration_profile",
    "melix.serving.capability.requested_mode": "requested_mode",
    "melix.serving.capability.resolved_mode": "resolved_mode",
    "melix.serving.capability.optional_dependency_source": "optional_dependency_source",
    "melix.serving.capability.unsupported_reason": "unsupported_reason",
    "melix.serving.capability.ignored_flags": "ignored_flags",
    "melix.serving.capability.fallback_policy": "fallback_policy",
}
_CAPABILITY_RECEIPT_REQUIRED_FIELDS = frozenset(
    _CAPABILITY_AUDIT_TO_RECEIPT_FIELDS.values()
)
_CAPABILITY_RECEIPT_LIST_FIELDS = frozenset(
    ("capabilities", "input_modalities", "output_modalities", "ignored_flags")
)
_ACCELERATION_CONFIG_AUDIT_TO_RECEIPT_FIELDS = {
    "melix.serving.acceleration_config.schema_version": "schema_version",
    "melix.serving.acceleration_config.method": "method",
    "melix.serving.acceleration_config.requested_method": "requested_method",
    "melix.serving.acceleration_config.sidecar_model": "sidecar_model",
    "melix.serving.acceleration_config.num_speculative_tokens": (
        "num_speculative_tokens"
    ),
    "melix.serving.acceleration_config.profile": "profile",
    "melix.serving.acceleration_config.conflicting_flags": "conflicting_flags",
    "melix.serving.acceleration_config.controller_scope": "controller_scope",
    "melix.serving.acceleration_config.disabled_reason": "disabled_reason",
}
_ACCELERATION_CONFIG_RECEIPT_REQUIRED_FIELDS = frozenset(
    _ACCELERATION_CONFIG_AUDIT_TO_RECEIPT_FIELDS.values()
)
_ACCELERATION_CONFIG_RECEIPT_LIST_FIELDS = frozenset(("conflicting_flags",))
_ACCELERATION_CONFIG_RECEIPT_INT_FIELDS = frozenset(("num_speculative_tokens",))
_MEMORY_ADMISSION_AUDIT_TO_RECEIPT_FIELDS = {
    "melix.serving.memory_admission.schema_version": "schema_version",
    "melix.serving.memory_admission.requested_context": "requested_context",
    "melix.serving.memory_admission.effective_context": "effective_context",
    "melix.serving.memory_admission.requested_batch": "requested_batch",
    "melix.serving.memory_admission.effective_batch": "effective_batch",
    "melix.serving.memory_admission.memory_headroom_bytes": (
        "memory_headroom_bytes"
    ),
    "melix.serving.memory_admission.estimated_active_bytes": (
        "estimated_active_bytes"
    ),
    "melix.serving.memory_admission.memory_telemetry_source": (
        "memory_telemetry_source"
    ),
    "melix.serving.memory_admission.admission_reason": "admission_reason",
    "melix.serving.memory_admission.fits_memory": "fits_memory",
}
_MEMORY_ADMISSION_RECEIPT_REQUIRED_FIELDS = frozenset(
    _MEMORY_ADMISSION_AUDIT_TO_RECEIPT_FIELDS.values()
)
_MEMORY_ADMISSION_RECEIPT_INT_FIELDS = frozenset(
    (
        "requested_context",
        "effective_context",
        "requested_batch",
        "effective_batch",
        "memory_headroom_bytes",
        "estimated_active_bytes",
    )
)
_MEMORY_ADMISSION_RECEIPT_BOOL_FIELDS = frozenset(("fits_memory",))
_EMPTY_EVENT_ATTRIBUTES: Mapping[str, object] = MappingProxyType({})
_JSON_COMPACT_SEPARATORS = (",", ":")
_JSONL_ENCODER = json.JSONEncoder(sort_keys=True, separators=_JSON_COMPACT_SEPARATORS)
_JSON_STRING_ENCODER = json.encoder.encode_basestring_ascii
_IS_FINITE = math.isfinite
_EMPTY_EVENT_JSON_DECODE_COMPLETED_PREFIX = b'{"attributes":{},"duration_ms":'
_EMPTY_EVENT_JSON_DECODE_COMPLETED_MID = b',"event_index":'
_EMPTY_EVENT_JSON_DECODE_COMPLETED_REQUEST_PREFIX = (
    b',"phase":"decode","request_id":'
)
_EMPTY_EVENT_JSON_DECODE_COMPLETED_SUFFIX = (
    b',"schema_version":"melix.serving_diagnostics.event.v1","status":"completed"}'
)
_EMPTY_EVENT_JSON_DECODE_COMPLETED_SUFFIX_LINE = _EMPTY_EVENT_JSON_DECODE_COMPLETED_SUFFIX + b"\n"
_EMPTY_EVENT_JSON_GENERIC_STATUS_PREFIX = (
    b',"schema_version":"melix.serving_diagnostics.event.v1","status":'
)


@lru_cache(maxsize=1024)
def _json_string_literal(value: str) -> str:
    return _JSON_STRING_ENCODER(value)


@lru_cache(maxsize=1024)
def _json_string_literal_bytes(value: str) -> bytes:
    return _JSON_STRING_ENCODER(value).encode("utf-8")


@lru_cache(maxsize=1024)
def _ascii_float_literal(value: float) -> bytes:
    return str(value).encode("ascii")


@lru_cache(maxsize=4096)
def _ascii_int_literal(value: int) -> bytes:
    return str(value).encode("ascii")


class ServingDiagnosticsComparisonError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ServingDiagnosticsQueueSnapshot:
    events: tuple[ServingDiagnosticsEvent, ...]
    dropped_count: int


class BoundedServingDiagnosticsEventQueue:
    __slots__ = (
        "_append_event",
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
        self._append_event = self._events.append
        self._dropped_count = 0
        self._is_saturated = False
        self._retained_count = 0
        self._lock = threading.Lock()

    def append(self, event: ServingDiagnosticsEvent) -> bool:
        lock = self._lock
        append_event = self._append_event
        lock.acquire()
        try:
            if self._is_saturated:
                append_event(event)
                self._dropped_count += 1
                return False
            append_event(event)
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
    native_acceleration: Mapping[str, object] = _EMPTY_EVENT_ATTRIBUTES

    def to_dict(self) -> dict[str, object]:
        native_acceleration = self.native_acceleration
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
            "native_acceleration": {}
            if native_acceleration is _EMPTY_EVENT_ATTRIBUTES
            else _stable_json_object(native_acceleration),
        }


class ServingDiagnosticsEvent:
    __slots__ = (
        "_attributes",
        "_duration_ms",
        "_event_index",
        "_phase",
        "_request_id",
        "_status",
    )

    def __init__(
        self,
        request_id: str,
        phase: str,
        event_index: int,
        status: str,
        duration_ms: float = 0.0,
        attributes: Mapping[str, object] = _EMPTY_EVENT_ATTRIBUTES,
    ) -> None:
        self._request_id = request_id
        self._phase = phase
        self._event_index = event_index
        self._status = status
        self._duration_ms = duration_ms
        self._attributes = attributes

    @property
    def request_id(self) -> str:
        return self._request_id

    @property
    def phase(self) -> str:
        return self._phase

    @property
    def event_index(self) -> int:
        return self._event_index

    @property
    def status(self) -> str:
        return self._status

    @property
    def duration_ms(self) -> float:
        return self._duration_ms

    @property
    def attributes(self) -> Mapping[str, object]:
        return self._attributes

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ServingDiagnosticsEvent):
            return NotImplemented
        return (
            self._request_id,
            self._phase,
            self._event_index,
            self._status,
            self._duration_ms,
            self._attributes,
        ) == (
            other._request_id,
            other._phase,
            other._event_index,
            other._status,
            other._duration_ms,
            other._attributes,
        )

    __hash__ = None  # type: ignore[assignment]

    def to_dict(self) -> dict[str, object]:
        attributes = self._attributes
        event_index = self._event_index
        duration_ms = self._duration_ms
        return {
            "schema_version": SERVING_DIAGNOSTICS_EVENT_SCHEMA_VERSION,
            "request_id": self._request_id,
            "phase": self._phase,
            "event_index": event_index
            if type(event_index) is int
            else int(event_index),
            "status": self._status,
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
    serving_acceleration_config: Mapping[str, object] = _EMPTY_EVENT_ATTRIBUTES
    native_acceleration: Mapping[str, object] = _EMPTY_EVENT_ATTRIBUTES

    def to_dict(self) -> dict[str, object]:
        serving_acceleration_config = self.serving_acceleration_config
        native_acceleration = self.native_acceleration
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
            "serving_acceleration_config": _stable_json_object(
                serving_acceleration_config
            ),
            "native_acceleration": {}
            if native_acceleration is _EMPTY_EVENT_ATTRIBUTES
            else _stable_json_object(native_acceleration),
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

    diagnostics_root = output_root / "serving-diagnostics"
    diagnostics_root.mkdir(parents=True, exist_ok=True)
    bundle_root = diagnostics_root / _safe_artifact_id(bundle_id)
    bundle_root.mkdir(exist_ok=True)
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
    _write_json(
        effective_config_path,
        _effective_config_with_profile_receipt(effective_config),
    )
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
        "acceleration_configs": {
            "baseline": _stable_json_object(
                baseline.serving_acceleration_config
            ),
            "accelerated": _stable_json_object(
                accelerated.serving_acceleration_config
            ),
        },
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
    if not payload:
        return {}
    return {
        str(key): _stable_json_value(value)
        for key, value in sorted(payload.items(), key=lambda item: str(item[0]))
    }


def _effective_config_with_profile_receipt(
    effective_config: Mapping[str, object],
) -> dict[str, object]:
    if not effective_config:
        return {}
    stable_config = _stable_json_object(effective_config)
    enriched_config = dict(stable_config)
    metadata_sources = _effective_config_metadata_sources(stable_config)
    if "serving_profile" not in enriched_config:
        for metadata in metadata_sources:
            receipt = _serving_profile_receipt_from_audit_metadata(metadata)
            if receipt:
                enriched_config["serving_profile"] = receipt
                break
    if "serving_readiness" not in enriched_config:
        for metadata in metadata_sources:
            receipt = _serving_readiness_receipt_from_audit_metadata(metadata)
            if receipt:
                enriched_config["serving_readiness"] = receipt
                break
    if "serving_capability" not in enriched_config:
        for metadata in metadata_sources:
            receipt = _serving_capability_receipt_from_audit_metadata(metadata)
            if receipt:
                enriched_config["serving_capability"] = receipt
                break
    if "serving_acceleration_config" not in enriched_config:
        for metadata in metadata_sources:
            receipt = _serving_acceleration_config_receipt_from_audit_metadata(
                metadata
            )
            if receipt:
                enriched_config["serving_acceleration_config"] = receipt
                break
    if "serving_memory_admission" not in enriched_config:
        for metadata in metadata_sources:
            receipt = _serving_memory_admission_receipt_from_audit_metadata(
                metadata
            )
            if receipt:
                enriched_config["serving_memory_admission"] = receipt
                break
    if "network_fetch_policy" not in enriched_config:
        for metadata in metadata_sources:
            receipt = network_fetch_policy_receipt_from_metadata(metadata)
            if receipt:
                enriched_config["network_fetch_policy"] = receipt
                break
    if "privacy_audit_counters" not in enriched_config:
        for metadata in metadata_sources:
            counter = privacy_audit_counter_from_metadata(metadata)
            if counter:
                enriched_config["privacy_audit_counters"] = [counter]
                break
    if "privacy_detector_receipts" not in enriched_config:
        for metadata in metadata_sources:
            receipt = privacy_detector_receipt_from_metadata(metadata)
            if receipt:
                enriched_config["privacy_detector_receipts"] = [receipt]
                break
    if enriched_config == stable_config:
        return stable_config
    return {
        str(key): value
        for key, value in sorted(enriched_config.items(), key=lambda item: str(item[0]))
    }


def _effective_config_metadata_sources(
    effective_config: Mapping[str, object],
) -> tuple[Mapping[str, object], ...]:
    sources: list[Mapping[str, object]] = [effective_config]
    for container_key in ("execution_ext", "execution_metadata", "request_metadata", "metadata"):
        container = effective_config.get(container_key)
        if isinstance(container, Mapping):
            sources.append(container)
    execution = effective_config.get("execution")
    if isinstance(execution, Mapping):
        sources.append(execution)
        ext = execution.get("ext")
        if isinstance(ext, Mapping):
            sources.append(ext)
    worker_request = effective_config.get("worker_request")
    if isinstance(worker_request, Mapping):
        execution = worker_request.get("execution")
        if isinstance(execution, Mapping):
            sources.append(execution)
            ext = execution.get("ext")
            if isinstance(ext, Mapping):
                sources.append(ext)
    return tuple(sources)


def _serving_profile_receipt_from_audit_metadata(
    metadata: Mapping[str, object],
) -> dict[str, object]:
    receipt = {
        receipt_key: str(value)
        for audit_key, receipt_key in _PROFILE_AUDIT_TO_RECEIPT_FIELDS.items()
        if (value := metadata.get(audit_key)) is not None
    }
    if _PROFILE_RECEIPT_REQUIRED_FIELDS.issubset(receipt):
        return receipt
    return {}


def _serving_readiness_receipt_from_audit_metadata(
    metadata: Mapping[str, object],
) -> dict[str, object]:
    receipt = {
        receipt_key: str(value)
        for audit_key, receipt_key in _READINESS_AUDIT_TO_RECEIPT_FIELDS.items()
        if (value := metadata.get(audit_key)) is not None
    }
    if _READINESS_RECEIPT_REQUIRED_FIELDS.issubset(receipt):
        return receipt
    return {}


def _serving_capability_receipt_from_audit_metadata(
    metadata: Mapping[str, object],
) -> dict[str, object]:
    receipt: dict[str, object] = {}
    for audit_key, receipt_key in _CAPABILITY_AUDIT_TO_RECEIPT_FIELDS.items():
        value = metadata.get(audit_key)
        if value is None:
            continue
        if receipt_key in _CAPABILITY_RECEIPT_LIST_FIELDS:
            receipt[receipt_key] = _metadata_list(value)
        else:
            receipt[receipt_key] = str(value)
    if _CAPABILITY_RECEIPT_REQUIRED_FIELDS.issubset(receipt):
        return receipt
    return {}


def _serving_acceleration_config_receipt_from_audit_metadata(
    metadata: Mapping[str, object],
) -> dict[str, object]:
    receipt: dict[str, object] = {}
    for audit_key, receipt_key in _ACCELERATION_CONFIG_AUDIT_TO_RECEIPT_FIELDS.items():
        value = metadata.get(audit_key)
        if value is None:
            continue
        if receipt_key in _ACCELERATION_CONFIG_RECEIPT_LIST_FIELDS:
            receipt[receipt_key] = _metadata_list(value)
        elif receipt_key in _ACCELERATION_CONFIG_RECEIPT_INT_FIELDS:
            try:
                receipt[receipt_key] = int(str(value).strip())
            except ValueError:
                return {}
        else:
            receipt[receipt_key] = str(value)
    if _ACCELERATION_CONFIG_RECEIPT_REQUIRED_FIELDS.issubset(receipt):
        return receipt
    return {}


def _serving_memory_admission_receipt_from_audit_metadata(
    metadata: Mapping[str, object],
) -> dict[str, object]:
    receipt: dict[str, object] = {}
    for audit_key, receipt_key in _MEMORY_ADMISSION_AUDIT_TO_RECEIPT_FIELDS.items():
        value = metadata.get(audit_key)
        if value is None:
            continue
        if receipt_key in _MEMORY_ADMISSION_RECEIPT_INT_FIELDS:
            try:
                parsed = int(str(value).strip())
            except ValueError:
                return {}
            if parsed < 0:
                return {}
            receipt[receipt_key] = parsed
        elif receipt_key in _MEMORY_ADMISSION_RECEIPT_BOOL_FIELDS:
            parsed_bool = _metadata_bool(value)
            if parsed_bool is None:
                return {}
            receipt[receipt_key] = parsed_bool
        else:
            receipt[receipt_key] = str(value)
    if _MEMORY_ADMISSION_RECEIPT_REQUIRED_FIELDS.issubset(receipt):
        return receipt
    return {}


def _metadata_list(value: object) -> list[str]:
    if isinstance(value, (list, tuple)):
        raw_items = value
    elif isinstance(value, (set, frozenset)):
        raw_items = sorted(value, key=lambda item: str(item))
    else:
        raw_items = str(value).split(",")
    return [
        item_text
        for item in raw_items
        if item is not None and (item_text := str(item).strip())
    ]


def _metadata_bool(value: object) -> bool | None:
    return _bool_value(value)


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
    if not payload:
        path.write_bytes(b"{}\n")
        return
    path.write_bytes((_JSONL_ENCODER.encode(payload) + "\n").encode("utf-8"))


def _write_jsonl(path: Path, rows: Any) -> None:
    encode = _JSONL_ENCODER.encode
    event_type = ServingDiagnosticsEvent
    extend_empty_attribute_event = _extend_empty_attribute_event_json_line_bytes
    payload = bytearray()
    append_line = payload.extend
    newline = b"\n"
    request_id_literals: dict[str, bytes] = {}
    decode_completed_duration_prefixes: dict[float, bytes] = {}
    decode_completed_request_suffixes: dict[str, bytes] = {}
    for row in rows:
        if isinstance(row, event_type):
            if extend_empty_attribute_event(
                append_line,
                row,
                request_id_literals,
                decode_completed_duration_prefixes,
                decode_completed_request_suffixes,
            ):
                continue
            row = row.to_dict()
        append_line(encode(row).encode("utf-8"))
        append_line(newline)
    path.write_bytes(payload)


def _empty_attribute_event_json_line(
    event: ServingDiagnosticsEvent,
    request_id_literals: dict[str, str] | None = None,
) -> str | None:
    line = _empty_attribute_event_json_line_bytes(event, request_id_literals)
    if line is None:
        return None
    return line.decode("utf-8")


def _extend_empty_attribute_event_json_line_bytes(
    append_line: Any,
    event: ServingDiagnosticsEvent,
    request_id_literals: dict[str, bytes],
    decode_completed_duration_prefixes: dict[float, bytes] | None = None,
    decode_completed_request_suffixes: dict[str, bytes] | None = None,
) -> bool:
    if event._attributes is not _EMPTY_EVENT_ATTRIBUTES:
        return False
    event_index = event._event_index
    duration_ms = event._duration_ms
    if type(event_index) is not int or type(duration_ms) is not float:
        return False
    if not _IS_FINITE(duration_ms):
        return False
    phase = event._phase
    request_id = event._request_id
    status = event._status
    duration_literal = _ascii_float_literal(duration_ms)
    event_index_literal = _ascii_int_literal(event_index)
    if phase == "decode" and status == "completed":
        if decode_completed_duration_prefixes is None:
            decode_completed_duration_prefixes = {}
        if decode_completed_request_suffixes is None:
            decode_completed_request_suffixes = {}
        duration_prefix = decode_completed_duration_prefixes.get(duration_ms)
        if duration_prefix is None:
            duration_prefix = b"".join(
                (
                    _EMPTY_EVENT_JSON_DECODE_COMPLETED_PREFIX,
                    duration_literal,
                    _EMPTY_EVENT_JSON_DECODE_COMPLETED_MID,
                )
            )
            decode_completed_duration_prefixes[duration_ms] = duration_prefix
        request_suffix = decode_completed_request_suffixes.get(request_id)
        if request_suffix is None:
            encoded_request_id = request_id_literals.get(request_id)
            if encoded_request_id is None:
                encoded_request_id = _json_string_literal_bytes(request_id)
                request_id_literals[request_id] = encoded_request_id
            request_suffix = b"".join(
                (
                    _EMPTY_EVENT_JSON_DECODE_COMPLETED_REQUEST_PREFIX,
                    encoded_request_id,
                    _EMPTY_EVENT_JSON_DECODE_COMPLETED_SUFFIX_LINE,
                )
            )
            decode_completed_request_suffixes[request_id] = request_suffix
        append_line(duration_prefix)
        append_line(event_index_literal)
        append_line(request_suffix)
        return True
    encoded_request_id = request_id_literals.get(request_id)
    if encoded_request_id is None:
        encoded_request_id = _json_string_literal_bytes(request_id)
        request_id_literals[request_id] = encoded_request_id
    append_line(b'{"attributes":{},"duration_ms":')
    append_line(duration_literal)
    append_line(b',"event_index":')
    append_line(event_index_literal)
    append_line(b',"phase":')
    append_line(_json_string_literal_bytes(phase))
    append_line(b',"request_id":')
    append_line(encoded_request_id)
    append_line(_EMPTY_EVENT_JSON_GENERIC_STATUS_PREFIX)
    append_line(_json_string_literal_bytes(status))
    append_line(b"}\n")
    return True


def _empty_attribute_event_json_line_bytes(
    event: ServingDiagnosticsEvent,
    request_id_literals: dict[str, bytes] | None = None,
) -> bytes | None:
    if event._attributes is not _EMPTY_EVENT_ATTRIBUTES:
        return None
    event_index = event._event_index
    duration_ms = event._duration_ms
    if type(event_index) is not int or type(duration_ms) is not float:
        return None
    if not _IS_FINITE(duration_ms):
        return None
    phase = event._phase
    request_id = event._request_id
    status = event._status
    if request_id_literals is None:
        encoded_request_id = _json_string_literal_bytes(request_id)
    else:
        encoded_request_id = request_id_literals.get(request_id)
        if encoded_request_id is None:
            encoded_request_id = _json_string_literal_bytes(request_id)
            request_id_literals[request_id] = encoded_request_id
    if phase == "decode" and status == "completed":
        return b"".join(
            (
                _EMPTY_EVENT_JSON_DECODE_COMPLETED_PREFIX,
                _ascii_float_literal(duration_ms),
                _EMPTY_EVENT_JSON_DECODE_COMPLETED_MID,
                _ascii_int_literal(event_index),
                _EMPTY_EVENT_JSON_DECODE_COMPLETED_REQUEST_PREFIX,
                encoded_request_id,
                _EMPTY_EVENT_JSON_DECODE_COMPLETED_SUFFIX,
            )
        )
    return b"".join(
        (
            b'{"attributes":{},"duration_ms":',
            _ascii_float_literal(duration_ms),
            b',"event_index":',
            _ascii_int_literal(event_index),
            b',"phase":',
            _json_string_literal_bytes(phase),
            b',"request_id":',
            encoded_request_id,
            b',"schema_version":"melix.serving_diagnostics.event.v1","status":',
            _json_string_literal_bytes(status),
            b"}",
        )
    )
