from __future__ import annotations

import pytest

from worker.engine.evaluation_core import EvaluationCore


def test_agentic_judge_prompt_receipts_use_shared_prompt_context_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[object]] = []

    class Admission:
        user_payload = {"question": "Q", "tool_observations": []}
        untrusted_context_receipts = [
            {
                "schema_version": "melix.untrusted_context_receipt.v1",
                "segment_id": "sample-1:question",
                "source_type": "agentic_judge_user_payload",
                "source_field": "question",
                "message_role": "user",
                "trust_level": "untrusted",
                "policy": "data_only",
                "boundary_checked": True,
                "included": True,
                "owner_scope_checked": False,
                "reason": "sample-derived context is prompt data, not instructions",
                "corrective_action": "Keep this segment in the user payload and do not project it into system or developer instructions.",
            }
        ]

    def fake_admit(segments: list[object]) -> Admission:
        calls.append(segments)
        return Admission()

    monkeypatch.setattr(
        "worker.engine.evaluation_core.admit_prompt_context_segments",
        fake_admit,
    )

    receipts = EvaluationCore._agentic_judge_untrusted_context_receipts(
        sample_id="sample-1",
        user_payload={"question": "Q", "tool_observations": []},
    )

    assert receipts == Admission.untrusted_context_receipts
    assert len(calls) == 1
    segments = calls[0]
    assert [segment.segment_id for segment in segments] == [
        "sample-1:question",
        "sample-1:tool_observations",
    ]
    assert [segment.source_type for segment in segments] == [
        "agentic_judge_user_payload",
        "agentic_judge_user_payload",
    ]
    assert [segment.source_field for segment in segments] == [
        "question",
        "tool_observations",
    ]
    assert [segment.value for segment in segments] == ["Q", []]


def test_agentic_judge_refusal_receipts_use_shared_prompt_context_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_refusal(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"receipt": "from-shared-helper"}

    monkeypatch.setattr(
        "worker.engine.evaluation_core.refused_prompt_context_receipt",
        fake_refusal,
    )

    receipt = EvaluationCore._agentic_judge_refusal_receipt(
        source_field="hidden_gold",
        reason="unsupported_user_payload_field",
    )

    assert receipt == {"receipt": "from-shared-helper"}
    assert calls == [
        {
            "segment_id": "agentic_judge_user_payload:hidden_gold",
            "source_type": "agentic_judge_user_payload",
            "source_field": "hidden_gold",
            "reason": "unsupported_user_payload_field",
            "corrective_action": "Remove this field before projecting the sample-derived context into the judge user payload.",
        }
    ]
