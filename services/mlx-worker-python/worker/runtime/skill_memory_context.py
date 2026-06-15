from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal, Mapping, NoReturn

from worker.runtime.prompt_context import (
    PromptContextAdmission,
    PromptContextSourceEvidence,
    admit_prompt_context_source_evidence,
    refused_prompt_context_receipt,
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


@dataclass(frozen=True, slots=True)
class SkillMemoryLookupResultProjection:
    prompt_user_payload: dict[str, Any]
    untrusted_context_receipts: list[dict[str, object]]
    refusal_receipts: list[dict[str, object]]
    lookup_message: dict[str, Any] | None


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
    entries: Any,
) -> SkillMemoryContextProjection:
    entries_type = type(entries)
    if entries_type is not list and entries_type is not tuple:
        return SkillMemoryContextProjection(
            user_payload={},
            untrusted_context_receipts=[],
            refusal_receipts=[
                refused_source_prompt_context_receipt(
                    segment_id="unknown-skill:skill-context",
                    source_type="skill",
                    source_field="entries",
                    source_id="unknown-skill",
                    reason="invalid_skill_context_field",
                    corrective_action="Reject malformed skill context before prompt assembly.",
                )
            ],
        )
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


def project_skill_memory_store_records(records: Any) -> SkillMemoryContextProjection:
    records_type = type(records)
    if records_type is not list and records_type is not tuple:
        return SkillMemoryContextProjection(
            user_payload={},
            untrusted_context_receipts=[],
            refusal_receipts=[
                _store_record_refusal(
                    source_field="records",
                    source_id="unknown-skill",
                    context_kind="skill",
                )
            ],
        )

    entries: list[SkillMemoryContextEntry] = []
    refusal_receipts: list[dict[str, object]] = []

    for record in records:
        if not isinstance(record, Mapping):
            refusal_receipts.append(
                _store_record_refusal(
                    source_field="record",
                    source_id="unknown-skill",
                    context_kind="skill",
                )
            )
            continue

        context_kind = record.get("context_kind")
        if context_kind not in ("skill", "memory"):
            source_id = _store_record_source_id(record)
            refusal_context_kind = _store_record_refusal_context_kind(source_id)
            refusal_receipts.append(
                _store_record_refusal(
                    source_field="context_kind",
                    source_id=source_id,
                    context_kind=refusal_context_kind,
                )
            )
            continue

        entries.append(
            SkillMemoryContextEntry(
                context_kind=context_kind,
                source_id=record.get("source_id"),
                payload=record.get("payload"),
                owner_scope_checked=record.get("owner_scope_checked"),
                segment_id=record.get("segment_id", ""),
                source_field=record.get("source_field", ""),
                reason=record.get("reason", ""),
                corrective_action=record.get("corrective_action", ""),
            )
        )

    projection = project_skill_memory_contexts(entries)
    return SkillMemoryContextProjection(
        user_payload=projection.user_payload,
        untrusted_context_receipts=projection.untrusted_context_receipts,
        refusal_receipts=[
            *(dict(receipt) for receipt in refusal_receipts),
            *(dict(receipt) for receipt in projection.refusal_receipts),
        ],
    )


def project_skill_memory_lookup_result(
    lookup_result: Any,
    *,
    lookup_source_id: Any = "",
    lookup_segment_id: Any = "",
    lookup_source_field: Any = "",
) -> SkillMemoryLookupResultProjection:
    wrapper_metadata_refusal = _lookup_result_metadata_refusal(
        lookup_source_id=lookup_source_id,
        lookup_segment_id=lookup_segment_id,
        lookup_source_field=lookup_source_field,
    )
    if wrapper_metadata_refusal is not None:
        return SkillMemoryLookupResultProjection(
            prompt_user_payload={},
            untrusted_context_receipts=[],
            refusal_receipts=[wrapper_metadata_refusal],
            lookup_message=None,
        )
    normalized_lookup_source_id = _lookup_metadata_text_or_default(
        lookup_source_id,
        default="unknown-skill-memory-lookup",
    )
    normalized_lookup_segment_id = _lookup_metadata_text_or_default(
        lookup_segment_id,
        default=f"{normalized_lookup_source_id}:lookup-result",
    )
    normalized_lookup_source_field = _lookup_metadata_text_or_default(
        lookup_source_field,
        default="lookup_result",
    )
    has_lookup_metadata = (
        lookup_source_id != "" or lookup_segment_id != "" or lookup_source_field != ""
    )
    if not isinstance(lookup_result, Mapping):
        return SkillMemoryLookupResultProjection(
            prompt_user_payload={},
            untrusted_context_receipts=[],
            refusal_receipts=[
                _lookup_result_refusal(
                    source_id=normalized_lookup_source_id,
                    segment_id=normalized_lookup_segment_id,
                    source_field=normalized_lookup_source_field,
                )
            ],
            lookup_message=None,
        )

    store_projection = project_skill_memory_store_records(lookup_result.get("records"))
    prompt_user_payload = _copy_payload(store_projection.user_payload)
    untrusted_context_receipts = _copy_receipts(
        store_projection.untrusted_context_receipts
    )
    refusal_receipts = _copy_receipts(store_projection.refusal_receipts)
    if (
        has_lookup_metadata
        and "records" not in lookup_result
        and len(refusal_receipts) == 1
        and not prompt_user_payload
        and not untrusted_context_receipts
    ):
        refusal_receipts = [
            _lookup_result_refusal(
                source_id=normalized_lookup_source_id,
                segment_id=normalized_lookup_segment_id,
                source_field=normalized_lookup_source_field,
            )
        ]
    lookup_message: dict[str, Any] | None = None
    if prompt_user_payload:
        lookup_message = {
            "role": "user",
            "content": prompt_user_payload,
            "untrusted_context_receipts": untrusted_context_receipts,
        }

    return SkillMemoryLookupResultProjection(
        prompt_user_payload=prompt_user_payload,
        untrusted_context_receipts=untrusted_context_receipts,
        refusal_receipts=refusal_receipts,
        lookup_message=lookup_message,
    )


def _copy_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return deepcopy(dict(payload))


def _copy_receipts(receipts: list[dict[str, object]]) -> list[dict[str, object]]:
    # Receipt schemas are flat JSON metadata; payload-bearing values are never copied here.
    return [dict(receipt) for receipt in receipts]


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


def _store_record_source_id(record: Mapping[str, Any]) -> str:
    source_id = record.get("source_id")
    if isinstance(source_id, str) and source_id.strip():
        return source_id.strip()
    return "unknown-skill"


def _store_record_refusal_context_kind(source_id: str) -> ContextKind:
    if source_id.startswith("memory:"):
        return "memory"
    return "skill"


def _store_record_refusal(
    *,
    source_field: str,
    source_id: str,
    context_kind: ContextKind,
) -> dict[str, object]:
    return refused_source_prompt_context_receipt(
        segment_id=f"{source_id}:{context_kind}-context",
        source_type=context_kind,
        source_field=source_field,
        source_id=source_id,
        reason=f"invalid_{context_kind}_context_field",
        corrective_action=f"Reject malformed {context_kind} context before prompt assembly.",
    )


def _lookup_result_refusal(
    *,
    source_id: str = "unknown-skill-memory-lookup",
    segment_id: str = "unknown-skill-memory-lookup:lookup-result",
    source_field: str = "lookup_result",
) -> dict[str, object]:
    return refused_prompt_context_receipt(
        segment_id=segment_id,
        source_type="skill_memory_lookup",
        source_field=source_field,
        source_id=source_id,
        reason="invalid_skill_memory_lookup_result",
        corrective_action="Reject malformed skill or memory lookup result before prompt assembly.",
    )


def _lookup_result_metadata_refusal(
    *,
    lookup_source_id: Any,
    lookup_segment_id: Any,
    lookup_source_field: Any,
) -> dict[str, object] | None:
    fallback_source_id = "unknown-skill-memory-lookup"
    fallback_segment_id = f"{fallback_source_id}:lookup-result"
    if not _valid_lookup_metadata_text(lookup_source_id):
        return _lookup_result_refusal(
            source_id=fallback_source_id,
            segment_id=fallback_segment_id,
            source_field="lookup_source_id",
        )
    normalized_source_id = _lookup_metadata_text_or_default(
        lookup_source_id,
        default=fallback_source_id,
    )
    normalized_segment_id = f"{normalized_source_id}:lookup-result"
    if not _valid_lookup_metadata_text(lookup_segment_id):
        return _lookup_result_refusal(
            source_id=normalized_source_id,
            segment_id=normalized_segment_id,
            source_field="lookup_segment_id",
        )
    normalized_segment_id = _lookup_metadata_text_or_default(
        lookup_segment_id,
        default=normalized_segment_id,
    )
    if not _valid_lookup_metadata_text(lookup_source_field):
        return _lookup_result_refusal(
            source_id=normalized_source_id,
            segment_id=normalized_segment_id,
            source_field="lookup_source_field",
        )
    return None


def _valid_lookup_metadata_text(value: Any) -> bool:
    return value == "" or (isinstance(value, str) and bool(value.strip()))


def _lookup_metadata_text_or_default(value: Any, *, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


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
    "SkillMemoryLookupResultProjection",
    "SkillMemoryContextProjection",
    "admit_memory_context",
    "admit_skill_context",
    "project_skill_memory_contexts",
    "project_skill_memory_lookup_result",
    "project_skill_memory_store_records",
]
