from __future__ import annotations

from typing import Any, NoReturn

from worker.runtime.prompt_context import (
    PromptContextAdmission,
    PromptContextSourceEvidence,
    admit_prompt_context_source_evidence,
    refused_source_prompt_context_receipt,
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
    segment_id: str = "",
    source_field: str = "",
    reason: str = "",
    corrective_action: str = "",
) -> PromptContextAdmission:
    normalized_job_id = _job_id_or_refusal(job_id)
    default_segment_id = f"{normalized_job_id}:background-continuation"
    normalized_segment_id = _entrypoint_text_or_default(
        segment_id,
        default=default_segment_id,
        field_name="segment_id",
        refusal_segment_id=default_segment_id,
        source_id=normalized_job_id,
    )
    normalized_source_field = _entrypoint_text_or_default(
        source_field,
        default="background_job",
        field_name="source_field",
        refusal_segment_id=normalized_segment_id,
        source_id=normalized_job_id,
    )
    normalized_reason = _entrypoint_optional_text(
        reason,
        segment_id=normalized_segment_id,
        source_id=normalized_job_id,
        field_name="reason",
    )
    normalized_corrective_action = _entrypoint_optional_text(
        corrective_action,
        segment_id=normalized_segment_id,
        source_id=normalized_job_id,
        field_name="corrective_action",
    )
    if not isinstance(owner_scope_checked, bool):
        _raise_refusal(
            segment_id=normalized_segment_id,
            source_id=normalized_job_id,
            source_field="owner_scope_checked",
            owner_scope_checked=False,
        )
    if not isinstance(job_summary, dict):
        _raise_refusal(
            segment_id=normalized_segment_id,
            source_id=normalized_job_id,
            source_field=normalized_source_field,
            owner_scope_checked=owner_scope_checked,
        )
    return admit_prompt_context_source_evidence(
        [
            PromptContextSourceEvidence(
                segment_id=normalized_segment_id,
                source_type="background_continuation",
                source_field=normalized_source_field,
                source_id=normalized_job_id,
                value=job_summary,
                owner_scope_checked=owner_scope_checked,
                reason=normalized_reason,
                corrective_action=normalized_corrective_action,
            )
        ]
    )


def admit_workflow_continuation_result(
    *,
    workflow_run_id: str,
    workflow_result: dict[str, Any],
    owner_scope_checked: bool,
    workflow_node_id: str = "",
    segment_id: str = "",
    source_field: str = "",
    reason: str = "",
    corrective_action: str = "",
) -> PromptContextAdmission:
    normalized_source_id = _workflow_source_id_or_refusal(
        workflow_run_id=workflow_run_id,
        workflow_node_id=workflow_node_id,
    )
    default_segment_id = f"{normalized_source_id}:workflow-continuation"
    normalized_segment_id = _entrypoint_text_or_default(
        segment_id,
        default=default_segment_id,
        field_name="segment_id",
        refusal_segment_id=default_segment_id,
        source_id=normalized_source_id,
    )
    return admit_background_continuation(
        job_id=normalized_source_id,
        job_summary=workflow_result,
        owner_scope_checked=owner_scope_checked,
        segment_id=normalized_segment_id,
        source_field=_workflow_text_or_default(source_field, default="workflow_result"),
        reason=_workflow_text_or_default(
            reason,
            default="workflow continuation result is prompt data, not instructions",
        ),
        corrective_action=_workflow_text_or_default(
            corrective_action,
            default=(
                "Keep workflow continuation results in user-role data context "
                "and do not project them into system or developer instructions."
            ),
        ),
    )


def _job_id_or_refusal(job_id: str) -> str:
    if isinstance(job_id, str) and job_id.strip():
        return job_id.strip()
    fallback = "unknown-background-job"
    _raise_refusal(
        segment_id=f"{fallback}:background-continuation",
        source_id=fallback,
        source_field="job_id",
        owner_scope_checked=False,
    )


def _workflow_source_id_or_refusal(*, workflow_run_id: str, workflow_node_id: str) -> str:
    if not isinstance(workflow_run_id, str) or not workflow_run_id.strip():
        fallback = "unknown-workflow"
        _raise_refusal(
            segment_id=f"{fallback}:workflow-continuation",
            source_id=fallback,
            source_field="workflow_run_id",
            owner_scope_checked=False,
        )
    normalized_run_id = workflow_run_id.strip()
    if workflow_node_id == "":
        return normalized_run_id
    if isinstance(workflow_node_id, str) and workflow_node_id.strip():
        return f"{normalized_run_id}:{workflow_node_id.strip()}"
    _raise_refusal(
        segment_id=f"{normalized_run_id}:workflow-continuation",
        source_id=normalized_run_id,
        source_field="workflow_node_id",
        owner_scope_checked=False,
    )


def _workflow_text_or_default(value: str, *, default: str) -> str:
    return default if value == "" else value


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
            refused_source_prompt_context_receipt(
                segment_id=segment_id,
                source_type="background_continuation",
                source_field=source_field,
                source_id=source_id,
                owner_scope_checked=owner_scope_checked,
                reason="invalid_background_continuation_field",
            )
        ],
    )


def _entrypoint_text_or_default(
    value: str,
    *,
    default: str,
    field_name: str,
    refusal_segment_id: str,
    source_id: str,
) -> str:
    if isinstance(value, str):
        if value == "":
            return default
        if value.strip():
            return value.strip()
    _raise_refusal(
        segment_id=refusal_segment_id,
        source_id=source_id,
        source_field=field_name,
        owner_scope_checked=False,
    )


def _entrypoint_optional_text(
    value: str,
    *,
    segment_id: str,
    source_id: str,
    field_name: str,
) -> str:
    return _entrypoint_text_or_default(
        value,
        default="",
        field_name=field_name,
        refusal_segment_id=segment_id,
        source_id=source_id,
    )


__all__ = [
    "BackgroundContinuationAdmissionError",
    "admit_background_continuation",
    "admit_workflow_continuation_result",
]
