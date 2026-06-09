from __future__ import annotations

from typing import Any, NoReturn

from worker.runtime.prompt_context import (
    PromptContextAdmission,
    PromptContextSegment,
    admit_prompt_context_segments,
    refused_prompt_context_receipt,
)


class BackgroundContinuationAdmissionError(ValueError):
    def __init__(self, message: str, *, refusal_receipts: list[dict[str, object]]) -> None:
        super().__init__(message)
        self.refusal_receipts = refusal_receipts


def admit_background_continuation(
    *,
    job_id: str,
    job_summary: dict[str, Any],
    owner_scope_checked: bool,
) -> PromptContextAdmission:
    normalized_job_id = _job_id_or_refusal(job_id)
    segment_id = f"{normalized_job_id}:background-continuation"
    if not isinstance(owner_scope_checked, bool):
        _raise_refusal(
            segment_id=segment_id,
            source_id=normalized_job_id,
            source_field="owner_scope_checked",
            owner_scope_checked=False,
        )
    if not isinstance(job_summary, dict):
        _raise_refusal(
            segment_id=segment_id,
            source_id=normalized_job_id,
            source_field="background_job",
            owner_scope_checked=owner_scope_checked,
        )
    return admit_prompt_context_segments(
        [
            PromptContextSegment(
                segment_id=segment_id,
                source_type="background_continuation",
                source_field="background_job",
                source_id=normalized_job_id,
                value=job_summary,
                owner_scope_checked=owner_scope_checked,
                reason="background continuation is prompt data, not instructions",
                corrective_action=(
                    "Keep background job follow-up context in user-role data context "
                    "and do not project it into system or developer instructions."
                ),
            )
        ]
    )


def _job_id_or_refusal(job_id: str) -> str:
    if isinstance(job_id, str) and job_id.strip():
        return job_id
    fallback = "unknown-background-job"
    _raise_refusal(
        segment_id=f"{fallback}:background-continuation",
        source_id=fallback,
        source_field="job_id",
        owner_scope_checked=False,
    )


def _raise_refusal(
    *,
    segment_id: str,
    source_id: str,
    source_field: str,
    owner_scope_checked: bool,
) -> NoReturn:
    raise BackgroundContinuationAdmissionError(
        "Invalid background continuation context.",
        refusal_receipts=[
            refused_prompt_context_receipt(
                segment_id=segment_id,
                source_type="background_continuation",
                source_field=source_field,
                source_id=source_id,
                owner_scope_checked=owner_scope_checked,
                reason="invalid_background_continuation_field",
                corrective_action=(
                    "Reject malformed background continuation context before prompt assembly."
                ),
            )
        ],
    )


__all__ = [
    "BackgroundContinuationAdmissionError",
    "admit_background_continuation",
]
