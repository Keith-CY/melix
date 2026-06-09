from __future__ import annotations

from typing import Any, Literal, NoReturn

from worker.runtime.prompt_context import (
    PromptContextAdmission,
    PromptContextSegment,
    admit_prompt_context_segments,
    refused_prompt_context_receipt,
)


ContextKind = Literal["skill", "memory"]


class SkillMemoryContextAdmissionError(ValueError):
    def __init__(self, message: str, *, refusal_receipts: list[dict[str, object]]) -> None:
        super().__init__(message)
        self.refusal_receipts = refusal_receipts


def admit_skill_context(
    *,
    skill_id: str,
    skill_payload: dict[str, Any],
    owner_scope_checked: bool,
) -> PromptContextAdmission:
    return _admit_context(
        context_kind="skill",
        source_id=skill_id,
        payload=skill_payload,
        owner_scope_checked=owner_scope_checked,
    )


def admit_memory_context(
    *,
    memory_id: str,
    memory_payload: dict[str, Any],
    owner_scope_checked: bool,
) -> PromptContextAdmission:
    return _admit_context(
        context_kind="memory",
        source_id=memory_id,
        payload=memory_payload,
        owner_scope_checked=owner_scope_checked,
    )


def _admit_context(
    *,
    context_kind: ContextKind,
    source_id: str,
    payload: dict[str, Any],
    owner_scope_checked: bool,
) -> PromptContextAdmission:
    normalized_source_id = _source_id_or_refusal(context_kind, source_id)
    segment_id = f"{normalized_source_id}:{context_kind}-context"
    if not isinstance(owner_scope_checked, bool):
        _raise_refusal(
            context_kind=context_kind,
            segment_id=segment_id,
            source_id=normalized_source_id,
            source_field="owner_scope_checked",
            owner_scope_checked=False,
        )
    if not isinstance(payload, dict):
        _raise_refusal(
            context_kind=context_kind,
            segment_id=segment_id,
            source_id=normalized_source_id,
            source_field=context_kind,
            owner_scope_checked=owner_scope_checked,
        )
    return admit_prompt_context_segments(
        [
            PromptContextSegment(
                segment_id=segment_id,
                source_type=context_kind,
                source_field=context_kind,
                source_id=normalized_source_id,
                value=payload,
                owner_scope_checked=owner_scope_checked,
                reason=f"{context_kind} evidence is prompt data, not instructions",
                corrective_action=(
                    f"Keep {context_kind} evidence in user-role data context and do not project it "
                    "into system or developer instructions."
                ),
            )
        ]
    )


def _source_id_or_refusal(context_kind: ContextKind, source_id: str) -> str:
    if isinstance(source_id, str) and source_id.strip():
        return source_id
    fallback = f"unknown-{context_kind}"
    _raise_refusal(
        context_kind=context_kind,
        segment_id=f"{fallback}:{context_kind}-context",
        source_id=fallback,
        source_field=f"{context_kind}_id",
        owner_scope_checked=False,
    )


def _raise_refusal(
    *,
    context_kind: ContextKind,
    segment_id: str,
    source_id: str,
    source_field: str,
    owner_scope_checked: bool,
) -> NoReturn:
    raise SkillMemoryContextAdmissionError(
        f"Invalid {context_kind} context.",
        refusal_receipts=[
            refused_prompt_context_receipt(
                segment_id=segment_id,
                source_type=context_kind,
                source_field=source_field,
                source_id=source_id,
                owner_scope_checked=owner_scope_checked,
                reason=f"invalid_{context_kind}_context_field",
                corrective_action=f"Reject malformed {context_kind} context before prompt assembly.",
            )
        ],
    )


__all__ = [
    "SkillMemoryContextAdmissionError",
    "admit_memory_context",
    "admit_skill_context",
]
