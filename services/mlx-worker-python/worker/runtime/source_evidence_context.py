from __future__ import annotations

from typing import Any, Literal, NoReturn

from worker.runtime.prompt_context import (
    PromptContextAdmission,
    PromptContextSourceEvidence,
    admit_prompt_context_source_evidence,
    refused_source_prompt_context_receipt,
)


SourceEvidenceKind = Literal["skill", "memory"]


class SourceEvidenceAdmissionError(ValueError):
    def __init__(self, message: str, *, refusal_receipts: list[dict[str, object]]) -> None:
        super().__init__(message)
        self.refusal_receipts = refusal_receipts


def admit_skill_evidence(
    *,
    skill_id: str,
    payload: dict[str, Any],
    owner_scope_checked: bool,
) -> PromptContextAdmission:
    return _admit_source_evidence(
        source_type="skill",
        source_id=skill_id,
        payload=payload,
        owner_scope_checked=owner_scope_checked,
    )


def admit_memory_evidence(
    *,
    memory_id: str,
    payload: dict[str, Any],
    owner_scope_checked: bool,
) -> PromptContextAdmission:
    return _admit_source_evidence(
        source_type="memory",
        source_id=memory_id,
        payload=payload,
        owner_scope_checked=owner_scope_checked,
    )


def _admit_source_evidence(
    *,
    source_type: SourceEvidenceKind,
    source_id: Any,
    payload: Any,
    owner_scope_checked: Any,
) -> PromptContextAdmission:
    fallback_source_id = f"unknown-{source_type}"
    source_field = f"{source_type}_evidence"
    normalized_source_id = _source_id_or_refusal(
        source_type=source_type,
        source_id=source_id,
        fallback_source_id=fallback_source_id,
    )
    segment_id = f"{normalized_source_id}:{source_type}-evidence"
    if not isinstance(owner_scope_checked, bool):
        _raise_refusal(
            source_type=source_type,
            segment_id=segment_id,
            source_id=normalized_source_id,
            source_field="owner_scope_checked",
            owner_scope_checked=False,
        )
    if not isinstance(payload, dict):
        _raise_refusal(
            source_type=source_type,
            segment_id=segment_id,
            source_id=normalized_source_id,
            source_field=source_field,
            owner_scope_checked=owner_scope_checked,
        )
    return admit_prompt_context_source_evidence(
        [
            PromptContextSourceEvidence(
                segment_id=segment_id,
                source_type=source_type,
                source_field=source_field,
                source_id=normalized_source_id,
                value=payload,
                owner_scope_checked=owner_scope_checked,
            )
        ]
    )


def _source_id_or_refusal(
    *,
    source_type: SourceEvidenceKind,
    source_id: Any,
    fallback_source_id: str,
) -> str:
    if isinstance(source_id, str) and source_id.strip():
        return source_id
    _raise_refusal(
        source_type=source_type,
        segment_id=f"{fallback_source_id}:{source_type}-evidence",
        source_id=fallback_source_id,
        source_field=f"{source_type}_id",
        owner_scope_checked=False,
    )


def _raise_refusal(
    *,
    source_type: SourceEvidenceKind,
    segment_id: str,
    source_id: str,
    source_field: str,
    owner_scope_checked: bool,
) -> NoReturn:
    raise SourceEvidenceAdmissionError(
        f"Invalid {source_type} evidence context.",
        refusal_receipts=[
            refused_source_prompt_context_receipt(
                segment_id=segment_id,
                source_type=source_type,
                source_field=source_field,
                source_id=source_id,
                owner_scope_checked=owner_scope_checked,
                reason=f"invalid_{source_type}_evidence_field",
            )
        ],
    )


__all__ = [
    "SourceEvidenceAdmissionError",
    "SourceEvidenceKind",
    "admit_memory_evidence",
    "admit_skill_evidence",
]
