from __future__ import annotations

from worker.runtime.untrusted_context import (
    UNTRUSTED_CONTEXT_RECEIPT_SCHEMA_VERSION,
    untrusted_context_receipt,
)


def test_untrusted_context_receipt_records_admitted_user_data_boundary() -> None:
    receipt = untrusted_context_receipt(
        segment_id="sample-1:tool_observations",
        source_type="agentic_judge_user_payload",
        source_field="tool_observations",
        included=True,
        reason="sample-derived context is prompt data, not instructions",
        corrective_action=(
            "Keep this segment in the user payload and do not project it into "
            "system or developer instructions."
        ),
    )

    assert UNTRUSTED_CONTEXT_RECEIPT_SCHEMA_VERSION == "melix.untrusted_context_receipt.v1"
    assert receipt == {
        "schema_version": "melix.untrusted_context_receipt.v1",
        "segment_id": "sample-1:tool_observations",
        "source_type": "agentic_judge_user_payload",
        "source_field": "tool_observations",
        "message_role": "user",
        "trust_level": "untrusted",
        "policy": "data_only",
        "boundary_checked": True,
        "included": True,
        "owner_scope_checked": False,
        "reason": "sample-derived context is prompt data, not instructions",
        "corrective_action": (
            "Keep this segment in the user payload and do not project it into "
            "system or developer instructions."
        ),
    }


def test_untrusted_context_receipt_records_refused_user_data_boundary() -> None:
    receipt = untrusted_context_receipt(
        segment_id="agentic_judge_user_payload:hidden_gold",
        source_type="agentic_judge_user_payload",
        source_field="hidden_gold",
        included=False,
        reason="unsupported_user_payload_field",
        corrective_action=(
            "Remove this field before projecting the sample-derived context "
            "into the judge user payload."
        ),
    )

    assert receipt["included"] is False
    assert receipt["boundary_checked"] is True
    assert receipt["policy"] == "data_only"
    assert receipt["message_role"] == "user"
    assert receipt["reason"] == "unsupported_user_payload_field"


def test_untrusted_context_receipt_can_attach_source_id_for_retrieved_segments() -> None:
    receipt = untrusted_context_receipt(
        segment_id="retrieved-docs:doc-7:text",
        source_type="retrieved_document",
        source_field="text",
        source_id="doc-7",
        included=True,
        owner_scope_checked=True,
        reason="retrieved document is prompt data, not instructions",
        corrective_action="Keep retrieved document text in user data segments only.",
    )

    assert receipt["source_id"] == "doc-7"
    assert receipt["owner_scope_checked"] is True
    assert receipt["trust_level"] == "untrusted"
