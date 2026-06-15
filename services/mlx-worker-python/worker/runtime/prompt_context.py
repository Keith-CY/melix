from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from worker.runtime.untrusted_context import untrusted_context_receipt


PromptContextMessageRole = Literal["user"]
PromptContextSourceType = Literal[
    "retrieved_document",
    "retrieved_image",
    "skill",
    "memory",
    "background_continuation",
    "tool_output",
]


class PromptContextBoundaryError(ValueError):
    pass


@dataclass(frozen=True)
class PromptContextSegment:
    segment_id: str
    source_type: str
    source_field: str
    value: Any
    reason: str
    corrective_action: str
    source_id: str = ""
    message_role: PromptContextMessageRole = "user"
    owner_scope_checked: bool = False

    def __post_init__(self) -> None:
        _require_text(self.segment_id, "segment_id")
        _require_text(self.source_type, "source_type")
        _require_text(self.source_field, "source_field")
        _require_text(self.reason, "reason")
        _require_text(self.corrective_action, "corrective_action")
        _require_text_type(self.source_id, "source_id")
        _require_bool(self.owner_scope_checked, "owner_scope_checked")
        if self.message_role != "user":
            raise PromptContextBoundaryError("Untrusted prompt context message_role must be user.")

    def receipt(self) -> dict[str, object]:
        return untrusted_context_receipt(
            segment_id=self.segment_id,
            source_type=self.source_type,
            source_field=self.source_field,
            source_id=self.source_id,
            message_role=self.message_role,
            owner_scope_checked=self.owner_scope_checked,
            included=True,
            reason=self.reason,
            corrective_action=self.corrective_action,
        )


@dataclass(frozen=True)
class PromptContextAdmission:
    user_payload: dict[str, Any]
    untrusted_context_receipts: list[dict[str, object]]

    @property
    def untrusted_context_receipt_count(self) -> int:
        return len(self.untrusted_context_receipts)


_SOURCE_CONTEXT_POLICIES: dict[str, tuple[str, str, str]] = {
    "retrieved_document": (
        "retrieved document evidence is prompt data, not instructions",
        "Keep retrieved document evidence in user-role data context and do not project it into system or developer instructions.",
        "Reject malformed retrieved document evidence before prompt assembly.",
    ),
    "retrieved_image": (
        "retrieved image evidence is prompt data, not instructions",
        "Keep retrieved image evidence in user-role data context and do not project it into system or developer instructions.",
        "Reject malformed retrieved image evidence before prompt assembly.",
    ),
    "skill": (
        "skill evidence is prompt data, not instructions",
        "Keep skill evidence in user-role data context and do not project it into system or developer instructions.",
        "Reject malformed skill evidence before prompt assembly.",
    ),
    "memory": (
        "memory evidence is prompt data, not instructions",
        "Keep memory evidence in user-role data context and do not project it into system or developer instructions.",
        "Reject malformed memory evidence before prompt assembly.",
    ),
    "background_continuation": (
        "background continuation is prompt data, not instructions",
        "Keep background continuation evidence in user-role data context and do not project it into system or developer instructions.",
        "Reject malformed background continuation evidence before prompt assembly.",
    ),
    "tool_output": (
        "tool output is prompt data, not instructions",
        "Keep tool output in user-role data context and do not project it into system or developer instructions.",
        "Reject malformed tool output before prompt assembly.",
    ),
}


@dataclass(frozen=True)
class PromptContextSourceEvidence:
    segment_id: str
    source_type: PromptContextSourceType
    source_field: str
    value: Any
    source_id: str = ""
    owner_scope_checked: bool = False
    reason: str = ""
    corrective_action: str = ""

    def __post_init__(self) -> None:
        _require_text(self.segment_id, "segment_id")
        _source_context_policy(self.source_type)
        _require_text(self.source_field, "source_field")
        _require_text_type(self.source_id, "source_id")
        _require_bool(self.owner_scope_checked, "owner_scope_checked")
        _require_optional_text(self.reason, "reason")
        _require_optional_text(self.corrective_action, "corrective_action")

    def as_segment(self) -> PromptContextSegment:
        default_reason, default_corrective_action, _ = _source_context_policy(self.source_type)
        return PromptContextSegment(
            segment_id=self.segment_id,
            source_type=self.source_type,
            source_field=self.source_field,
            value=self.value,
            source_id=self.source_id,
            owner_scope_checked=self.owner_scope_checked,
            reason=self.reason or default_reason,
            corrective_action=self.corrective_action or default_corrective_action,
        )


def admit_prompt_context_segments(segments: list[PromptContextSegment]) -> PromptContextAdmission:
    user_payload: dict[str, Any] = {}
    receipts: list[dict[str, object]] = []
    for segment in segments:
        if segment.source_field in user_payload:
            raise PromptContextBoundaryError(
                f"Duplicate untrusted prompt context source_field: {segment.source_field}"
            )
        user_payload[segment.source_field] = segment.value
        receipts.append(segment.receipt())
    return PromptContextAdmission(
        user_payload=user_payload,
        untrusted_context_receipts=receipts,
    )


def admit_prompt_context_source_evidence(
    evidence: list[PromptContextSourceEvidence],
) -> PromptContextAdmission:
    return admit_prompt_context_segments([item.as_segment() for item in evidence])


def refused_prompt_context_receipt(
    *,
    segment_id: str,
    source_type: str,
    source_field: str,
    reason: str,
    corrective_action: str,
    source_id: str = "",
    message_role: PromptContextMessageRole = "user",
    owner_scope_checked: bool = False,
) -> dict[str, object]:
    _require_text(segment_id, "segment_id")
    _require_text(source_type, "source_type")
    _require_text(source_field, "source_field")
    _require_text(reason, "reason")
    _require_text(corrective_action, "corrective_action")
    _require_text_type(source_id, "source_id")
    _require_bool(owner_scope_checked, "owner_scope_checked")
    if message_role != "user":
        raise PromptContextBoundaryError("Untrusted prompt context message_role must be user.")
    return untrusted_context_receipt(
        segment_id=segment_id,
        source_type=source_type,
        source_field=source_field,
        source_id=source_id,
        message_role=message_role,
        owner_scope_checked=owner_scope_checked,
        included=False,
        reason=reason,
        corrective_action=corrective_action,
    )


def refused_source_prompt_context_receipt(
    *,
    segment_id: str,
    source_type: PromptContextSourceType,
    source_field: str,
    reason: str,
    source_id: str = "",
    owner_scope_checked: bool = False,
    corrective_action: str = "",
) -> dict[str, object]:
    _, _, default_corrective_action = _source_context_policy(source_type)
    _require_optional_text(corrective_action, "corrective_action")
    return refused_prompt_context_receipt(
        segment_id=segment_id,
        source_type=source_type,
        source_field=source_field,
        source_id=source_id,
        owner_scope_checked=owner_scope_checked,
        reason=reason,
        corrective_action=corrective_action or default_corrective_action,
    )


def _source_context_policy(source_type: str) -> tuple[str, str, str]:
    _require_text(source_type, "source_type")
    policy = _SOURCE_CONTEXT_POLICIES.get(source_type)
    if policy is None:
        raise PromptContextBoundaryError(f"Unsupported prompt context source_type: {source_type}")
    return policy


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise PromptContextBoundaryError(f"Prompt context {field_name} must be non-empty.")


def _require_text_type(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise PromptContextBoundaryError(f"Prompt context {field_name} must be a string.")


def _require_optional_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise PromptContextBoundaryError(f"Prompt context {field_name} must be a string.")
    if value and not value.strip():
        raise PromptContextBoundaryError(f"Prompt context {field_name} must be non-empty.")


def _require_bool(value: bool, field_name: str) -> None:
    if not isinstance(value, bool):
        raise PromptContextBoundaryError(f"Prompt context {field_name} must be a boolean.")


__all__ = [
    "PromptContextAdmission",
    "PromptContextBoundaryError",
    "PromptContextMessageRole",
    "PromptContextSegment",
    "PromptContextSourceEvidence",
    "PromptContextSourceType",
    "admit_prompt_context_segments",
    "admit_prompt_context_source_evidence",
    "refused_prompt_context_receipt",
    "refused_source_prompt_context_receipt",
]
