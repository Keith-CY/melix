from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, NoReturn

from worker.runtime.prompt_context import (
    PromptContextAdmission,
    PromptContextSourceEvidence,
    admit_prompt_context_source_evidence,
    refused_source_prompt_context_receipt,
)


RetrievalContextKind = Literal["retrieved_document", "retrieved_image"]


class RetrievalContextAdmissionError(ValueError):
    def __init__(self, message: str, *, refusal_receipts: list[dict[str, object]]) -> None:
        super().__init__(message)
        self.refusal_receipts = refusal_receipts


@dataclass(frozen=True, slots=True)
class RetrievalContextEntry:
    context_kind: RetrievalContextKind
    source_id: str
    payload: dict[str, Any]
    owner_scope_checked: bool
    segment_id: str = ""
    source_field: str = ""
    reason: str = ""
    corrective_action: str = ""


@dataclass(frozen=True, slots=True)
class RetrievalContextProjection:
    user_payload: dict[str, Any]
    untrusted_context_receipts: list[dict[str, object]]
    refusal_receipts: list[dict[str, object]]

    @property
    def untrusted_context_receipt_count(self) -> int:
        return len(self.untrusted_context_receipts)


def admit_retrieved_document_context(
    *,
    document_id: str,
    document_payload: dict[str, Any],
    owner_scope_checked: bool,
    segment_id: str = "",
    source_field: str = "",
    reason: str = "",
    corrective_action: str = "",
) -> PromptContextAdmission:
    return _admit_context(
        context_kind="retrieved_document",
        source_id=document_id,
        payload=document_payload,
        owner_scope_checked=owner_scope_checked,
        segment_id=segment_id,
        source_field=source_field,
        reason=reason,
        corrective_action=corrective_action,
    )


def admit_retrieved_image_context(
    *,
    image_id: str,
    image_payload: dict[str, Any],
    owner_scope_checked: bool,
    segment_id: str = "",
    source_field: str = "",
    reason: str = "",
    corrective_action: str = "",
) -> PromptContextAdmission:
    return _admit_context(
        context_kind="retrieved_image",
        source_id=image_id,
        payload=image_payload,
        owner_scope_checked=owner_scope_checked,
        segment_id=segment_id,
        source_field=source_field,
        reason=reason,
        corrective_action=corrective_action,
    )


def project_retrieval_contexts(
    entries: list[RetrievalContextEntry] | tuple[RetrievalContextEntry, ...],
) -> RetrievalContextProjection:
    user_payload: dict[str, Any] = {}
    receipts: list[dict[str, object]] = []
    refusal_receipts: list[dict[str, object]] = []

    for entry in entries:
        try:
            admission = _admit_entry(entry)
        except RetrievalContextAdmissionError as exc:
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

    return RetrievalContextProjection(
        user_payload=user_payload,
        untrusted_context_receipts=receipts,
        refusal_receipts=refusal_receipts,
    )


def _admit_entry(entry: RetrievalContextEntry) -> PromptContextAdmission:
    if not isinstance(entry, RetrievalContextEntry):
        _raise_refusal(
            context_kind="retrieved_document",
            segment_id="unknown-retrieved-document:retrieved-document-context",
            source_id="unknown-retrieved-document",
            source_field="entry",
            owner_scope_checked=False,
        )
    if entry.context_kind == "retrieved_document":
        return admit_retrieved_document_context(
            document_id=entry.source_id,
            document_payload=entry.payload,
            owner_scope_checked=entry.owner_scope_checked,
            segment_id=entry.segment_id,
            source_field=entry.source_field,
            reason=entry.reason,
            corrective_action=entry.corrective_action,
        )
    if entry.context_kind == "retrieved_image":
        return admit_retrieved_image_context(
            image_id=entry.source_id,
            image_payload=entry.payload,
            owner_scope_checked=entry.owner_scope_checked,
            segment_id=entry.segment_id,
            source_field=entry.source_field,
            reason=entry.reason,
            corrective_action=entry.corrective_action,
        )
    fallback = _fallback_entry_source_id(entry)
    _raise_refusal(
        context_kind="retrieved_document",
        segment_id=f"{fallback}:retrieved-document-context",
        source_id=fallback,
        source_field="context_kind",
        owner_scope_checked=False,
    )


def _duplicate_projection_receipt(
    receipt: dict[str, object],
    *,
    duplicate_fields: list[str],
) -> dict[str, object]:
    source_type = receipt.get("source_type")
    if source_type not in ("retrieved_document", "retrieved_image"):
        source_type = "retrieved_document"
    source_field = receipt.get("source_field")
    if not isinstance(source_field, str) or source_field not in duplicate_fields:
        source_field = duplicate_fields[0]
    segment_id = receipt.get("segment_id")
    if not isinstance(segment_id, str) or not segment_id.strip():
        source_id = receipt.get("source_id")
        fallback = (
            source_id
            if isinstance(source_id, str) and source_id
            else _fallback_source_id(source_type)
        )
        segment_id = f"{fallback}:{_segment_suffix(source_type)}"
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
            "Provide a unique source_field before projecting multiple "
            "retrieved entries into one prompt payload."
        ),
    )


def _fallback_entry_source_id(entry: RetrievalContextEntry) -> str:
    if isinstance(entry.source_id, str) and entry.source_id.strip():
        return entry.source_id.strip()
    return "unknown-retrieved-document"


def _admit_context(
    *,
    context_kind: RetrievalContextKind,
    source_id: Any,
    payload: Any,
    owner_scope_checked: Any,
    segment_id: str,
    source_field: str,
    reason: str,
    corrective_action: str,
) -> PromptContextAdmission:
    normalized_source_id = _source_id_or_refusal(context_kind, source_id)
    normalized_segment_id = _entrypoint_text_or_default(
        context_kind,
        segment_id,
        default=f"{normalized_source_id}:{_segment_suffix(context_kind)}",
        field_name="segment_id",
        refusal_segment_id=f"{normalized_source_id}:{_segment_suffix(context_kind)}",
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


def _source_id_or_refusal(context_kind: RetrievalContextKind, source_id: Any) -> str:
    if isinstance(source_id, str) and source_id.strip():
        return source_id.strip()
    fallback = _fallback_source_id(context_kind)
    _raise_refusal(
        context_kind=context_kind,
        segment_id=f"{fallback}:{_segment_suffix(context_kind)}",
        source_id=fallback,
        source_field=_id_field(context_kind),
        owner_scope_checked=False,
    )


def _raise_refusal(
    *,
    context_kind: RetrievalContextKind,
    segment_id: str,
    source_id: str,
    source_field: str,
    owner_scope_checked: bool,
) -> NoReturn:
    raise RetrievalContextAdmissionError(
        f"Invalid {context_kind.replace('_', ' ')} context.",
        refusal_receipts=[
            refused_source_prompt_context_receipt(
                segment_id=segment_id,
                source_type=context_kind,
                source_field=source_field,
                source_id=source_id,
                owner_scope_checked=owner_scope_checked,
                reason=f"invalid_{context_kind}_context_field",
            )
        ],
    )


def _fallback_source_id(context_kind: RetrievalContextKind) -> str:
    if context_kind == "retrieved_document":
        return "unknown-retrieved-document"
    return "unknown-retrieved-image"


def _id_field(context_kind: RetrievalContextKind) -> str:
    if context_kind == "retrieved_document":
        return "retrieved_document_id"
    return "retrieved_image_id"


def _segment_suffix(context_kind: RetrievalContextKind) -> str:
    if context_kind == "retrieved_document":
        return "retrieved-document-context"
    return "retrieved-image-context"


def _entrypoint_text_or_default(
    context_kind: RetrievalContextKind,
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
    raise RetrievalContextAdmissionError(
        f"Invalid retrieved context {field_name}.",
        refusal_receipts=[
            refused_source_prompt_context_receipt(
                segment_id=refusal_segment_id,
                source_type=context_kind,
                source_field=field_name,
                source_id=source_id,
                reason=f"invalid_{context_kind}_context_field",
            )
        ],
    )


def _entrypoint_optional_text(
    context_kind: RetrievalContextKind,
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
    "RetrievalContextAdmissionError",
    "RetrievalContextEntry",
    "RetrievalContextProjection",
    "admit_retrieved_document_context",
    "admit_retrieved_image_context",
    "project_retrieval_contexts",
]
