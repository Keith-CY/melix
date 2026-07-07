from __future__ import annotations

import hashlib
import re

UNTRUSTED_CONTEXT_RECEIPT_SCHEMA_VERSION = "melix.untrusted_context_receipt.v1"
_PUBLIC_SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,96}$")
_SOURCE_ID_PREFIX = "source:"
_SOURCE_ID_PREFIX_LENGTH = len(_SOURCE_ID_PREFIX)


def untrusted_context_receipt(
    *,
    segment_id: str,
    source_type: str,
    source_field: str,
    included: bool,
    reason: str,
    corrective_action: str,
    source_id: str = "",
    message_role: str = "user",
    owner_scope_checked: bool = False,
) -> dict[str, object]:
    redacted_source_id = _redacted_source_id(source_id)
    redacted_segment_id = _redacted_segment_id(
        segment_id,
        source_id=source_id,
        redacted_source_id=redacted_source_id,
    )
    receipt: dict[str, object] = {
        "schema_version": UNTRUSTED_CONTEXT_RECEIPT_SCHEMA_VERSION,
        "segment_id": redacted_segment_id,
        "source_type": source_type,
        "source_field": source_field,
        "message_role": message_role,
        "trust_level": "untrusted",
        "policy": "data_only",
        "boundary_checked": True,
        "included": included,
        "owner_scope_checked": owner_scope_checked,
        "reason": reason,
        "corrective_action": corrective_action,
    }
    if redacted_source_id:
        receipt["source_id"] = redacted_source_id
    return receipt


def _redacted_source_id(source_id: str) -> str:
    if not source_id:
        return ""
    normalized = source_id.strip()
    if not normalized:
        return ""
    if _is_public_source_id(normalized):
        return normalized
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    return f"source:{digest}"


def _redacted_segment_id(
    segment_id: str,
    *,
    source_id: str,
    redacted_source_id: str,
) -> str:
    normalized_source_id = source_id.strip()
    if not redacted_source_id or redacted_source_id == source_id:
        return segment_id
    if segment_id == source_id or segment_id == normalized_source_id:
        return redacted_source_id
    raw_prefix = f"{source_id}:"
    if segment_id.startswith(raw_prefix):
        return f"{redacted_source_id}:{segment_id[len(raw_prefix):]}"
    prefix = f"{normalized_source_id}:"
    if segment_id.startswith(prefix):
        return f"{redacted_source_id}:{segment_id[len(prefix):]}"
    return segment_id


def _is_public_source_id(source_id: str) -> bool:
    if source_id.startswith(_SOURCE_ID_PREFIX):
        source_suffix = source_id[_SOURCE_ID_PREFIX_LENGTH:]
        if source_suffix.isdigit():
            return len(source_id) <= 96
    return _PUBLIC_SOURCE_ID_RE.fullmatch(source_id) is not None
