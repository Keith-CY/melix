from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from worker.runtime.untrusted_context import untrusted_context_receipt


PromptContextMessageRole = Literal["user"]


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


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise PromptContextBoundaryError(f"Prompt context {field_name} must be non-empty.")


__all__ = [
    "PromptContextAdmission",
    "PromptContextBoundaryError",
    "PromptContextMessageRole",
    "PromptContextSegment",
    "admit_prompt_context_segments",
    "refused_prompt_context_receipt",
]
