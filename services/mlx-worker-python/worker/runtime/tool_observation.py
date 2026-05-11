from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal


TOOL_OBSERVATION_SCHEMA_VERSION = "melix.agentic_tool_observation.v1"
SUPPORTED_TOOL_OBSERVATION_STATUSES = ("completed", "timeout", "failed")
DEFAULT_TOOL_OBSERVATION_TEXT_BYTE_LIMIT = 8192

ToolObservationStatus = Literal["completed", "timeout", "failed"]

_COMPACT_SORTED_JSON_ENCODER = json.JSONEncoder(
    ensure_ascii=False,
    separators=(",", ":"),
    sort_keys=True,
)


class ToolObservationError(ValueError):
    pass


@dataclass(frozen=True)
class ToolObservationPolicy:
    max_text_bytes: int = DEFAULT_TOOL_OBSERVATION_TEXT_BYTE_LIMIT
    redaction_terms: tuple[str, ...] = ()
    timeout_ms: int | None = None
    replay_seed: str = "melix.tool_observation.v1"

    def __post_init__(self) -> None:
        if self.max_text_bytes <= 0:
            raise ToolObservationError("Tool observation max_text_bytes must be positive.")
        if self.timeout_ms is not None and self.timeout_ms <= 0:
            raise ToolObservationError("Tool observation timeout_ms must be positive when set.")
        normalized_terms = tuple(
            dict.fromkeys(term for term in (term.strip() for term in self.redaction_terms) if term)
        )
        object.__setattr__(self, "redaction_terms", normalized_terms)
        object.__setattr__(self, "replay_seed", self.replay_seed.strip())
        if not self.replay_seed:
            raise ToolObservationError("Tool observation replay_seed must be non-empty.")

    def fingerprint_payload(self) -> dict[str, Any]:
        return {
            "max_text_bytes": self.max_text_bytes,
            "redaction_term_count": len(self.redaction_terms),
            "redaction_terms_hash": _sha256_json(self.redaction_terms),
            "timeout_ms": self.timeout_ms,
            "replay_seed": self.replay_seed,
        }

    def policy_hash(self) -> str:
        return _sha256_json(self.fingerprint_payload())


@dataclass(frozen=True)
class ToolObservationMetrics:
    record_count: int
    redacted_value_count: int
    truncated_count: int
    timeout_count: int
    original_bytes: int
    emitted_bytes: int

    def as_dict(self) -> dict[str, int]:
        return {
            "tool_observation.record_count": self.record_count,
            "tool_observation.redacted_value_count": self.redacted_value_count,
            "tool_observation.truncated_count": self.truncated_count,
            "tool_observation.timeout_count": self.timeout_count,
            "tool_observation.original_bytes": self.original_bytes,
            "tool_observation.emitted_bytes": self.emitted_bytes,
        }


@dataclass(frozen=True)
class ToolObservationReplayMetadata:
    schema_version: str
    policy_hash: str
    payload_hash: str
    fingerprint: str

    def as_dict(self) -> dict[str, str]:
        return {
            "schema_version": self.schema_version,
            "policy_hash": self.policy_hash,
            "payload_hash": self.payload_hash,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True)
class ToolObservationRecord:
    tool_name: str
    tool_call_id: str
    observation_kind: str
    status: ToolObservationStatus
    payload: dict[str, Any]
    metrics: ToolObservationMetrics
    replay: ToolObservationReplayMetadata
    timeout_ms: int | None = None

    def as_agentic_trace_observation(self) -> dict[str, Any]:
        observation: dict[str, Any] = {
            "schema_version": self.replay.schema_version,
            "tool_name": self.tool_name,
            "tool_call_id": self.tool_call_id,
            "observation_kind": self.observation_kind,
            "status": self.status,
            "payload": self.payload,
            "metrics": self.metrics.as_dict(),
            "replay": self.replay.as_dict(),
        }
        if self.timeout_ms is not None:
            observation["timeout_ms"] = self.timeout_ms
        return observation


@dataclass(frozen=True)
class _SanitizedPayload:
    value: Any
    redacted_value_count: int
    truncated_count: int
    original_bytes: int
    emitted_bytes: int


def normalize_tool_observation(
    *,
    tool_name: str,
    tool_call_id: str,
    observation_kind: str,
    status: ToolObservationStatus,
    payload: Any,
    policy: ToolObservationPolicy | None = None,
    schema_version: str = TOOL_OBSERVATION_SCHEMA_VERSION,
) -> ToolObservationRecord:
    normalized_tool_name = _required_text(tool_name, "tool_name")
    normalized_tool_call_id = _required_text(tool_call_id, "tool_call_id")
    normalized_observation_kind = _required_text(observation_kind, "observation_kind")
    normalized_status = _normalize_status(status)
    normalized_schema_version = _required_text(schema_version, "schema_version")
    observation_policy = policy or ToolObservationPolicy()

    sanitized = _sanitize_payload(payload, observation_policy)
    normalized_payload = _payload_dict(sanitized.value)
    timeout_ms = observation_policy.timeout_ms if normalized_status == "timeout" else None
    metrics = ToolObservationMetrics(
        record_count=1,
        redacted_value_count=sanitized.redacted_value_count,
        truncated_count=sanitized.truncated_count,
        timeout_count=1 if normalized_status == "timeout" else 0,
        original_bytes=sanitized.original_bytes,
        emitted_bytes=sanitized.emitted_bytes,
    )
    replay = _build_replay_metadata(
        schema_version=normalized_schema_version,
        policy=observation_policy,
        tool_name=normalized_tool_name,
        tool_call_id=normalized_tool_call_id,
        observation_kind=normalized_observation_kind,
        status=normalized_status,
        payload=normalized_payload,
    )
    return ToolObservationRecord(
        tool_name=normalized_tool_name,
        tool_call_id=normalized_tool_call_id,
        observation_kind=normalized_observation_kind,
        status=normalized_status,
        payload=normalized_payload,
        metrics=metrics,
        replay=replay,
        timeout_ms=timeout_ms,
    )


def _sanitize_payload(value: Any, policy: ToolObservationPolicy) -> _SanitizedPayload:
    if isinstance(value, dict):
        sanitized_items: dict[str, Any] = {}
        totals = _SanitizedPayload({}, 0, 0, 0, 0)
        for raw_key, raw_item in value.items():
            key = _sanitize_text(str(raw_key), policy)
            item = _sanitize_payload(raw_item, policy)
            if key.value in sanitized_items:
                raise ToolObservationError(f"Duplicate sanitized observation payload key: {key.value}")
            sanitized_items[key.value] = item.value
            totals = _merge_sanitized(totals, key, sanitized_items)
            totals = _merge_sanitized(totals, item, sanitized_items)
        return totals
    if isinstance(value, (list, tuple)):
        sanitized_values: list[Any] = []
        totals = _SanitizedPayload([], 0, 0, 0, 0)
        for raw_item in value:
            item = _sanitize_payload(raw_item, policy)
            sanitized_values.append(item.value)
            totals = _merge_sanitized(totals, item, sanitized_values)
        return totals
    if isinstance(value, str):
        return _sanitize_text(value, policy)
    if value is None or isinstance(value, (bool, int, float)):
        return _SanitizedPayload(value, 0, 0, 0, 0)
    return _sanitize_text(str(value), policy)


def _sanitize_text(value: str, policy: ToolObservationPolicy) -> _SanitizedPayload:
    original_bytes = len(value.encode("utf-8"))
    redacted = value
    redacted_value_count = 0
    for term in policy.redaction_terms:
        replacement_count = redacted.count(term)
        if replacement_count:
            redacted = redacted.replace(term, "[REDACTED]")
            redacted_value_count += replacement_count
    truncated, was_truncated = _truncate_utf8(redacted, policy.max_text_bytes)
    return _SanitizedPayload(
        value=truncated,
        redacted_value_count=redacted_value_count,
        truncated_count=1 if was_truncated else 0,
        original_bytes=original_bytes,
        emitted_bytes=len(truncated.encode("utf-8")),
    )


def _truncate_utf8(value: str, max_bytes: int) -> tuple[str, bool]:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value, False
    truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return truncated, True


def _merge_sanitized(
    totals: _SanitizedPayload,
    item: _SanitizedPayload,
    merged_value: Any,
) -> _SanitizedPayload:
    return _SanitizedPayload(
        value=merged_value,
        redacted_value_count=totals.redacted_value_count + item.redacted_value_count,
        truncated_count=totals.truncated_count + item.truncated_count,
        original_bytes=totals.original_bytes + item.original_bytes,
        emitted_bytes=totals.emitted_bytes + item.emitted_bytes,
    )


def _payload_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and value:
        return value
    if isinstance(value, str) and value.strip():
        return {"text": value}
    if isinstance(value, list) and value:
        return {"items": value}
    if value is not None and isinstance(value, (bool, int, float)):
        return {"value": value}
    raise ToolObservationError("Tool observation payload must be non-empty.")


def _build_replay_metadata(
    *,
    schema_version: str,
    policy: ToolObservationPolicy,
    tool_name: str,
    tool_call_id: str,
    observation_kind: str,
    status: ToolObservationStatus,
    payload: dict[str, Any],
) -> ToolObservationReplayMetadata:
    payload_hash = _sha256_json(payload)
    policy_hash = policy.policy_hash()
    fingerprint = _sha256_json(
        {
            "schema_version": schema_version,
            "policy_hash": policy_hash,
            "payload_hash": payload_hash,
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "observation_kind": observation_kind,
            "status": status,
            "replay_seed": policy.replay_seed,
        }
    )
    return ToolObservationReplayMetadata(
        schema_version=schema_version,
        policy_hash=policy_hash,
        payload_hash=payload_hash,
        fingerprint=fingerprint,
    )


def _normalize_status(status: str) -> ToolObservationStatus:
    normalized_status = status.strip()
    if normalized_status not in SUPPORTED_TOOL_OBSERVATION_STATUSES:
        joined = ", ".join(SUPPORTED_TOOL_OBSERVATION_STATUSES)
        raise ToolObservationError(f"Unsupported tool observation status: {status}. Expected one of: {joined}.")
    return normalized_status  # type: ignore[return-value]


def _required_text(value: str, field_name: str) -> str:
    normalized_value = value.strip()
    if not normalized_value:
        raise ToolObservationError(f"Tool observation {field_name} must be non-empty.")
    return normalized_value


def _sha256_json(payload: Any) -> str:
    encoded = _COMPACT_SORTED_JSON_ENCODER.encode(payload).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "DEFAULT_TOOL_OBSERVATION_TEXT_BYTE_LIMIT",
    "SUPPORTED_TOOL_OBSERVATION_STATUSES",
    "TOOL_OBSERVATION_SCHEMA_VERSION",
    "ToolObservationError",
    "ToolObservationMetrics",
    "ToolObservationPolicy",
    "ToolObservationRecord",
    "ToolObservationReplayMetadata",
    "ToolObservationStatus",
    "normalize_tool_observation",
]
