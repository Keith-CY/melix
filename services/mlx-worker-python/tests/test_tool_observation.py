from __future__ import annotations

import json

import pytest

from worker.runtime.tool_observation import (
    TOOL_OBSERVATION_SCHEMA_VERSION,
    ToolObservationError,
    ToolObservationPolicy,
    normalize_tool_observation,
)


def test_tool_observation_redacts_nested_payload_strings_without_leaking_terms() -> None:
    policy = ToolObservationPolicy(redaction_terms=("GOLD-SECRET", "oracle-token"))

    record = normalize_tool_observation(
        tool_name="image_crop",
        tool_call_id="call-1",
        observation_kind="image_region",
        status="completed",
        payload={
            "text": "Visible label GOLD-SECRET.",
            "oracle-token-key": "key should redact too",
            "items": [
                {"caption": "oracle-token appears twice: oracle-token"},
                "safe value",
            ],
        },
        policy=policy,
    )

    emitted = record.as_agentic_trace_observation()
    serialized = json.dumps(emitted, sort_keys=True)
    assert "GOLD-SECRET" not in serialized
    assert "oracle-token" not in serialized
    assert emitted["payload"]["text"] == "Visible label [REDACTED]."
    assert emitted["payload"]["[REDACTED]-key"] == "key should redact too"
    assert emitted["payload"]["items"][0]["caption"] == "[REDACTED] appears twice: [REDACTED]"
    assert emitted["metrics"]["tool_observation.redacted_value_count"] == 4
    assert emitted["metrics"]["tool_observation.truncated_count"] == 0


def test_tool_observation_truncates_utf8_safely_and_records_byte_metrics() -> None:
    record = normalize_tool_observation(
        tool_name="visit",
        tool_call_id="call-2",
        observation_kind="page_extract",
        status="completed",
        payload="AB界CD",
        policy=ToolObservationPolicy(max_text_bytes=4),
    )

    emitted = record.as_agentic_trace_observation()
    assert emitted["payload"] == {"text": "AB"}
    assert emitted["metrics"]["tool_observation.original_bytes"] == len("AB界CD".encode("utf-8"))
    assert emitted["metrics"]["tool_observation.emitted_bytes"] == 2
    assert emitted["metrics"]["tool_observation.truncated_count"] == 1


def test_tool_observation_timeout_status_records_explicit_metadata() -> None:
    record = normalize_tool_observation(
        tool_name="local_compute",
        tool_call_id="call-timeout",
        observation_kind="compute_result",
        status="timeout",
        payload={"text": "Timed out before result."},
        policy=ToolObservationPolicy(timeout_ms=250),
    )

    emitted = record.as_agentic_trace_observation()
    assert emitted["status"] == "timeout"
    assert emitted["timeout_ms"] == 250
    assert emitted["metrics"]["tool_observation.timeout_count"] == 1
    assert emitted["metrics"]["tool_observation.record_count"] == 1


def test_tool_observation_replay_fingerprint_is_stable_for_sanitized_payload() -> None:
    policy = ToolObservationPolicy(redaction_terms=("SECRET",))
    first = normalize_tool_observation(
        tool_name="text_search",
        tool_call_id="call-3",
        observation_kind="search_results",
        status="completed",
        payload={"text": "result SECRET"},
        policy=policy,
    )
    second = normalize_tool_observation(
        tool_name="text_search",
        tool_call_id="call-3",
        observation_kind="search_results",
        status="completed",
        payload={"text": "result SECRET"},
        policy=policy,
    )
    changed = normalize_tool_observation(
        tool_name="text_search",
        tool_call_id="call-3",
        observation_kind="search_results",
        status="completed",
        payload={"text": "different SECRET"},
        policy=policy,
    )

    assert first.replay.schema_version == TOOL_OBSERVATION_SCHEMA_VERSION
    assert first.replay.fingerprint == second.replay.fingerprint
    assert first.replay.payload_hash == second.replay.payload_hash
    assert first.replay.payload_hash != changed.replay.payload_hash
    assert first.replay.fingerprint != changed.replay.fingerprint


def test_tool_observation_replay_fingerprint_changes_with_call_identity() -> None:
    first = normalize_tool_observation(
        tool_name="text_search",
        tool_call_id="call-a",
        observation_kind="search_results",
        status="completed",
        payload={"text": "same"},
    )
    second = normalize_tool_observation(
        tool_name="text_search",
        tool_call_id="call-b",
        observation_kind="search_results",
        status="completed",
        payload={"text": "same"},
    )

    assert first.replay.payload_hash == second.replay.payload_hash
    assert first.replay.fingerprint != second.replay.fingerprint


def test_tool_observation_policy_hash_changes_with_redaction_terms() -> None:
    first = ToolObservationPolicy(redaction_terms=("SECRET-A",))
    second = ToolObservationPolicy(redaction_terms=("SECRET-B",))

    assert first.policy_hash() != second.policy_hash()


@pytest.mark.parametrize(
    ("policy_kwargs", "message"),
    [
        ({"max_text_bytes": 0}, "Tool observation max_text_bytes must be positive."),
        ({"timeout_ms": 0}, "Tool observation timeout_ms must be positive when set."),
        ({"replay_seed": " "}, "Tool observation replay_seed must be non-empty."),
    ],
)
def test_tool_observation_policy_rejects_invalid_values(
    policy_kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ToolObservationError, match=message):
        ToolObservationPolicy(**policy_kwargs)


def test_tool_observation_rejects_invalid_status() -> None:
    with pytest.raises(ToolObservationError, match="Unsupported tool observation status"):
        normalize_tool_observation(
            tool_name="visit",
            tool_call_id="call-4",
            observation_kind="page_extract",
            status="cancelled",  # type: ignore[arg-type]
            payload={"text": "cancelled"},
        )


@pytest.mark.parametrize(
    ("field_name", "kwargs"),
    [
        ("tool_name", {"tool_name": " "}),
        ("tool_call_id", {"tool_call_id": " "}),
        ("observation_kind", {"observation_kind": " "}),
        ("schema_version", {"schema_version": " "}),
    ],
)
def test_tool_observation_rejects_blank_identity_fields(
    field_name: str,
    kwargs: dict[str, str],
) -> None:
    payload = {
        "tool_name": "visit",
        "tool_call_id": "call-5",
        "observation_kind": "page_extract",
        "status": "completed",
        "payload": {"text": "ok"},
    }
    payload.update(kwargs)

    with pytest.raises(ToolObservationError, match=f"Tool observation {field_name} must be non-empty."):
        normalize_tool_observation(**payload)


@pytest.mark.parametrize("payload", ["", "  ", {}, []])
def test_tool_observation_rejects_empty_payload(payload: object) -> None:
    with pytest.raises(ToolObservationError, match="Tool observation payload must be non-empty."):
        normalize_tool_observation(
            tool_name="visit",
            tool_call_id="call-6",
            observation_kind="page_extract",
            status="completed",
            payload=payload,
        )
