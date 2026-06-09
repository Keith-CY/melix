from __future__ import annotations

UNTRUSTED_CONTEXT_RECEIPT_SCHEMA_VERSION = "melix.untrusted_context_receipt.v1"


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
    receipt: dict[str, object] = {
        "schema_version": UNTRUSTED_CONTEXT_RECEIPT_SCHEMA_VERSION,
        "segment_id": segment_id,
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
    if source_id:
        receipt["source_id"] = source_id
    return receipt
