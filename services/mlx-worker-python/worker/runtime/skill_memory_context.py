from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, NoReturn

from worker.runtime.prompt_context import (
    PromptContextAdmission,
    PromptContextSourceEvidence,
    admit_prompt_context_source_evidence,
    refused_source_prompt_context_receipt,
)


ContextKind = Literal["skill", "memory"]


class SkillMemoryContextAdmissionError(ValueError):
    def __init__(self, message: str, *, refusal_receipts: list[dict[str, object]]) -> None:
        super().__init__(message)
        self.refusal_receipts = refusal_receipts


@dataclass(frozen=True, slots=True)
class SkillMemoryContextEntry:
    context_kind: ContextKind
    source_id: str
    payload: dict[str, Any]
    owner_scope_checked: bool
    segment_id: str = ""
    source_field: str = ""
    reason: str = ""
    corrective_action: str = ""


@dataclass(frozen=True, slots=True)
class SkillMemoryContextProjection:
    user_payload: dict[str, Any]
    untrusted_context_receipts: list[dict[str, object]]
    refusal_receipts: list[dict[str, object]]

    @property
    def untrusted_context_receipt_count(self) -> int:
        return len(self.untrusted_context_receipts)


def admit_skill_context(
    *,
    skill_id: str,
    skill_payload: dict[str, Any],
    owner_scope_checked: bool,
    segment_id: str = "",
    source_field: str = "",
    reason: str = "",
    corrective_action: str = "",
) -> PromptContextAdmission:
    return _admit_context(
        context_kind="skill",
        source_id=skill_id,
        payload=skill_payload,
        owner_scope_checked=owner_scope_checked,
        segment_id=segment_id,
        source_field=source_field,
        reason=reason,
        corrective_action=corrective_action,
    )


def admit_memory_context(
    *,
    memory_id: str,
    memory_payload: dict[str, Any],
    owner_scope_checked: bool,
    segment_id: str = "",
    source_field: str = "",
    reason: str = "",
    corrective_action: str = "",
) -> PromptContextAdmission:
    return _admit_context(
        context_kind="memory",
        source_id=memory_id,
        payload=memory_payload,
        owner_scope_checked=owner_scope_checked,
        segment_id=segment_id,
        source_field=source_field,
        reason=reason,
        corrective_action=corrective_action,
    )


def project_skill_memory_contexts(
    entries: list[SkillMemoryContextEntry] | tuple[SkillMemoryContextEntry, ...],
) -> SkillMemoryContextProjection:
    user_payload: dict[str, Any] = {}
    receipts: list[dict[str, object]] = []
    refusal_receipts: list[dict[str, object]] = []

    for entry in entries:
        try:
            admission = _admit_entry(entry)
        except SkillMemoryContextAdmissionError as exc:
            refusal_receipts.extend(dict(receipt) for receipt in exc.refusal_receipts)
            continue

        duplicate_fields = [
            source_field
            for source_field in admission.user_payload
            if source_field in user_payload
        ]
        if duplicate_fields:
            refusal_receipts.extend(
                _duplicate_projection_receipt(
                    receipt,
                    duplicate_fields=duplicate_fields,
                )
                for receipt in admission.untrusted_context_receipts
            )
            continue

        user_payload.update(dict(admission.user_payload))
        receipts.extend(dict(receipt) for receipt in admission.untrusted_context_receipts)

    return SkillMemoryContextProjection(
        user_payload=user_payload,
        untrusted_context_receipts=receipts,
        refusal_receipts=refusal_receipts,
    )


def _admit_entry(entry: SkillMemoryContextEntry) -> PromptContextAdmission:
    if not isinstance(entry, SkillMemoryContextEntry):
        _raise_refusal(
            context_kind="skill",
            segment_id="unknown-skill:skill-context",
            source_id="unknown-skill",
            source_field="entry",
            owner_scope_checked=False,
        )
    if entry.context_kind == "skill":
        return admit_skill_context(
            skill_id=entry.source_id,
            skill_payload=entry.payload,
            owner_scope_checked=entry.owner_scope_checked,
            segment_id=entry.segment_id,
            source_field=entry.source_field,
            reason=entry.reason,
            corrective_action=entry.corrective_action,
        )
    if entry.context_kind == "memory":
        return admit_memory_context(
            memory_id=entry.source_id,
            memory_payload=entry.payload,
            owner_scope_checked=entry.owner_scope_checked,
            segment_id=entry.segment_id,
            source_field=entry.source_field,
            reason=entry.reason,
            corrective_action=entry.corrective_action,
        )
    _raise_refusal(
        context_kind="skill",
        segment_id=f"{_fallback_entry_source_id(entry)}:skill-context",
        source_id=_fallback_entry_source_id(entry),
        source_field="context_kind",
        owner_scope_checked=False,
    )


def _duplicate_projection_receipt(
    receipt: dict[str, object],
    *,
    duplicate_fields: list[str],
) -> dict[str, object]:
    source_type = receipt.get("source_type")
    if source_type not in ("skill", "memory"):
        source_type = "skill"
    source_field = receipt.get("source_field")
    if not isinstance(source_field, str) or source_field not in duplicate_fields:
        source_field = duplicate_fields[0]
    segment_id = receipt.get("segment_id")
    if not isinstance(segment_id, str) or not segment_id.strip():
        source_id = receipt.get("source_id")
        fallback = source_id if isinstance(source_id, str) and source_id else "unknown-skill"
        segment_id = f"{fallback}:{source_type}-context"
    source_id = receipt.get("source_id")
    owner_scope_checked = receipt.get("owner_scope_checked")
    return refused_source_prompt_context_receipt(
        segment_id=segment_id,
        source_type=source_type,
        source_field=source_field,
        source_id=source_id if isinstance(source_id, str) else "",
        owner_scope_checked=(
            owner_scope_checked if isinstance(owner_scope_checked, bool) else False
        ),
        reason=f"duplicate_{source_type}_context_field",
        corrective_action=(
            "Provide a unique source_field before projecting multiple skill "
            "or memory entries into one prompt payload."
        ),
    )


def _fallback_entry_source_id(entry: SkillMemoryContextEntry) -> str:
    if isinstance(entry.source_id, str) and entry.source_id.strip():
        return entry.source_id.strip()
    return "unknown-skill"


def _admit_context(
    *,
    context_kind: ContextKind,
    source_id: Any,
    payload: Any,
    owner_scope_checked: Any,
    segment_id: str,
    source_field: str,
    reason: str,
    corrective_action: str,
) -> PromptContextAdmission:
    normalized_source_id = _source_id_or_refusal(context_kind, source_id)
    default_segment_id = f"{normalized_source_id}:{context_kind}-context"
    normalized_segment_id = _entrypoint_text_or_default(
        context_kind,
        segment_id,
        default=default_segment_id,
        field_name="segment_id",
        refusal_segment_id=default_segment_id,
        source_id=normalized_source_id,
    )
    normalized_source_field = _entrypoint_text_or_default(
        context_kind,
        source_field,
        default=context_kind,
        field_name="source_field",
        refusal_segment_id=normalized_segment_id,
        source_id=normalized_source_id,
    )
    normalized_reason = _entrypoint_optional_text(
        context_kind,
        reason,
        segment_id=normalized_segment_id,
        source_id=normalized_source_id,
        field_name="reason",
    )
    normalized_corrective_action = _entrypoint_optional_text(
        context_kind,
        corrective_action,
        segment_id=normalized_segment_id,
        source_id=normalized_source_id,
        field_name="corrective_action",
    )
    if not isinstance(owner_scope_checked, bool):
        _raise_refusal(
            context_kind=context_kind,
            segment_id=normalized_segment_id,
            source_id=normalized_source_id,
            source_field="owner_scope_checked",
            owner_scope_checked=False,
        )
    if not isinstance(payload, dict):
        _raise_refusal(
            context_kind=context_kind,
            segment_id=normalized_segment_id,
            source_id=normalized_source_id,
            source_field=normalized_source_field,
            owner_scope_checked=owner_scope_checked,
        )
    return admit_prompt_context_source_evidence(
        [
            PromptContextSourceEvidence(
                segment_id=normalized_segment_id,
                source_type=context_kind,
                source_field=normalized_source_field,
                source_id=normalized_source_id,
                value=payload,
                owner_scope_checked=owner_scope_checked,
                reason=normalized_reason,
                corrective_action=normalized_corrective_action,
            )
        ]
    )


def _source_id_or_refusal(context_kind: ContextKind, source_id: Any) -> str:
    if isinstance(source_id, str) and source_id.strip():
        return source_id.strip()
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
            refused_source_prompt_context_receipt(
                segment_id=segment_id,
                source_type=context_kind,
                source_field=source_field,
                source_id=source_id,
                owner_scope_checked=owner_scope_checked,
                reason=f"invalid_{context_kind}_context_field",
                corrective_action=(
                    f"Reject malformed {context_kind} context before prompt assembly."
                ),
            )
        ],
    )


def _entrypoint_text_or_default(
    context_kind: ContextKind,
    value: str,
    *,
    default: str,
    field_name: str,
    refusal_segment_id: str,
    source_id: str,
) -> str:
    if value == "":
        return default
    if isinstance(value, str) and value.strip():
        return value.strip()
    _raise_refusal(
        context_kind=context_kind,
        segment_id=refusal_segment_id,
        source_id=source_id,
        source_field=field_name,
        owner_scope_checked=False,
    )


def _entrypoint_optional_text(
    context_kind: ContextKind,
    value: str,
    *,
    segment_id: str,
    source_id: str,
    field_name: str,
) -> str:
    return _entrypoint_text_or_default(
        context_kind,
        value,
        default="",
        field_name=field_name,
        refusal_segment_id=segment_id,
        source_id=source_id,
    )


__all__ = [
    "SkillMemoryContextEntry",
    "SkillMemoryContextAdmissionError",
    "SkillMemoryContextProjection",
    "admit_memory_context",
    "admit_skill_context",
    "project_skill_memory_contexts",
]
