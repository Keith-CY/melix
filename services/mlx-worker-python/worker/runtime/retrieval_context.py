from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, NoReturn

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
    entries: Any,
) -> RetrievalContextProjection:
    entries_type = type(entries)
    if entries_type is not list and entries_type is not tuple:
        return RetrievalContextProjection(
            user_payload={},
            untrusted_context_receipts=[],
            refusal_receipts=[
                refused_source_prompt_context_receipt(
                    segment_id="unknown-retrieved-document:retrieved-document-context",
                    source_type="retrieved_document",
                    source_field="entries",
                    source_id="unknown-retrieved-document",
                    reason="invalid_retrieved_document_context_field",
                )
            ],
        )
    user_payload: dict[str, Any] = {}
    receipts: list[dict[str, object]] = []
    refusal_receipts: list[dict[str, object]] = []
    admit_entry = _admit_entry
    duplicate_projection_receipt = _duplicate_projection_receipt
    refusal_receipts_extend = refusal_receipts.extend
    receipts_extend = receipts.extend
    receipts_append = receipts.append
    user_payload_update = user_payload.update
    copy_receipt = dict.copy

    for entry in entries:
        try:
            admission = admit_entry(entry)
        except RetrievalContextAdmissionError as exc:
            refusal_receipts_extend(copy_receipt(receipt) for receipt in exc.refusal_receipts)
            continue

        admission_payload = admission.user_payload
        if len(admission_payload) == 1:
            source_field = next(iter(admission_payload))
            if source_field in user_payload:
                refusal_receipts_extend(
                    duplicate_projection_receipt(
                        receipt,
                        duplicate_fields=[source_field],
                    )
                    for receipt in admission.untrusted_context_receipts
                )
                continue
            user_payload[source_field] = admission_payload[source_field]
        else:
            duplicate_fields: list[str] | None = None
            for source_field in admission_payload:
                if source_field in user_payload:
                    if duplicate_fields is None:
                        duplicate_fields = []
                    duplicate_fields.append(source_field)
            if duplicate_fields is not None:
                refusal_receipts_extend(
                    duplicate_projection_receipt(
                        receipt,
                        duplicate_fields=duplicate_fields,
                    )
                    for receipt in admission.untrusted_context_receipts
                )
                continue
            user_payload_update(admission_payload)
        admission_receipts = admission.untrusted_context_receipts
        if len(admission_receipts) == 1:
            receipts_append(copy_receipt(admission_receipts[0]))
        else:
            for receipt in admission_receipts:
                receipts_append(copy_receipt(receipt))

    return RetrievalContextProjection(
        user_payload=user_payload,
        untrusted_context_receipts=receipts,
        refusal_receipts=refusal_receipts,
    )


def project_retrieval_store_records(records: Any) -> RetrievalContextProjection:
    records_type = type(records)
    if records_type is not list and records_type is not tuple:
        return RetrievalContextProjection(
            user_payload={},
            untrusted_context_receipts=[],
            refusal_receipts=[
                _store_record_refusal(
                    source_field="records",
                    source_id="unknown-retrieved-document",
                    context_kind="retrieved_document",
                )
            ],
        )

    entries: list[RetrievalContextEntry] = []
    refusal_receipts: list[dict[str, object]] = []

    for record in records:
        if not isinstance(record, Mapping):
            refusal_receipts.append(
                _store_record_refusal(
                    source_field="record",
                    source_id="unknown-retrieved-document",
                    context_kind="retrieved_document",
                )
            )
            continue

        context_kind = record.get("context_kind")
        if context_kind not in ("retrieved_document", "retrieved_image"):
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
            RetrievalContextEntry(
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

    projection = project_retrieval_contexts(entries)
    return RetrievalContextProjection(
        user_payload=projection.user_payload,
        untrusted_context_receipts=projection.untrusted_context_receipts,
        refusal_receipts=[
            *(dict(receipt) for receipt in refusal_receipts),
            *(dict(receipt) for receipt in projection.refusal_receipts),
        ],
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


def _store_record_source_id(record: Mapping[str, Any]) -> str:
    source_id = record.get("source_id")
    if isinstance(source_id, str) and source_id.strip():
        return source_id.strip()
    return "unknown-retrieved-document"


def _store_record_refusal_context_kind(source_id: str) -> RetrievalContextKind:
    if source_id.startswith("image:"):
        return "retrieved_image"
    return "retrieved_document"


def _store_record_refusal(
    *,
    source_field: str,
    source_id: str,
    context_kind: RetrievalContextKind,
) -> dict[str, object]:
    return refused_source_prompt_context_receipt(
        segment_id=f"{source_id}:{_segment_suffix(context_kind)}",
        source_type=context_kind,
        source_field=source_field,
        source_id=source_id,
        reason=f"invalid_{context_kind}_context_field",
        corrective_action=(
            f"Reject malformed {context_kind.replace('_', ' ')} evidence before prompt assembly."
        ),
    )


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
    "project_retrieval_store_records",
]
