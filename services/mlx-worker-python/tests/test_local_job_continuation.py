from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from worker.runtime.background_continuation import (
    admit_background_continuation as original_admit_background_continuation,
)
from worker.runtime import local_job_continuation as local_job_continuation_module
from worker.runtime.local_job_continuation import (
    RECEIPT_SCHEMA_VERSION,
    RECORD_SCHEMA_VERSION,
    LocalJobContinuationAdmissionError,
    LocalJobContinuationRecord,
    LocalJobContinuationStore,
    LocalJobContinuationStoreError,
    LocalJobLiveEvidence,
    project_local_job_session_followup,
    reconcile_local_job_continuation,
)
from worker.runtime.prompt_context import PromptContextAdmission


def test_local_job_continuation_exports_are_sorted() -> None:
    assert local_job_continuation_module.__all__ == [
        "FOLLOWUP_STATUSES",
        "JOB_STATUSES",
        "RECEIPT_SCHEMA_VERSION",
        "RECORD_SCHEMA_VERSION",
        "LocalJobContinuationAdmissionError",
        "LocalJobContinuationFollowupCandidate",
        "LocalJobContinuationFollowupClaim",
        "LocalJobContinuationFollowupScan",
        "LocalJobContinuationRecord",
        "LocalJobContinuationReconciliation",
        "LocalJobContinuationStore",
        "LocalJobContinuationStoreError",
        "LocalJobLiveEvidence",
        "LocalJobSessionFollowupProjection",
        "claim_local_job_followup",
        "project_local_job_session_followup",
        "reconcile_local_job_continuation",
    ]


def _record(**overrides: object) -> LocalJobContinuationRecord:
    values: dict[str, object] = {
        "job_id": "job-7",
        "command": ("melix", "bench", "--suite", "smoke"),
        "cwd": "/workspace",
        "log_path": "/workspace/.runtime/jobs/job-7.log",
        "session_id": "session-7",
        "timeout_seconds": 120,
    }
    values.update(overrides)
    return LocalJobContinuationRecord(**values)  # type: ignore[arg-type]


def test_local_job_continuation_record_round_trips_through_store(tmp_path: Path) -> None:
    store = LocalJobContinuationStore(tmp_path)

    saved = store.save_record(
        _record(
            status="running",
            exit_status=None,
            followup_status="pending",
            followup_session_id="followup-1",
            followed_up_at="",
            success_marker_path="",
            artifact_paths=("/workspace/out/report.md",),
        )
    )
    loaded = store.load_record("job-7")

    assert saved.revision == 0
    assert loaded == saved
    payload = json.loads((tmp_path / "job-7.json").read_text(encoding="utf-8"))
    assert payload == {
        "schema_version": RECORD_SCHEMA_VERSION,
        "job_id": "job-7",
        "command": ["melix", "bench", "--suite", "smoke"],
        "cwd": "/workspace",
        "log_path": "/workspace/.runtime/jobs/job-7.log",
        "session_id": "session-7",
        "status": "running",
        "exit_status": None,
        "timeout_seconds": 120,
        "followup_status": "pending",
        "followup_session_id": "followup-1",
        "followed_up_at": "",
        "success_marker_path": "",
        "artifact_paths": ["/workspace/out/report.md"],
        "revision": 0,
    }


def test_stale_completed_record_with_live_progress_is_revived() -> None:
    result = reconcile_local_job_continuation(
        _record(status="completed", exit_status=0),
        live_evidence=LocalJobLiveEvidence(
            session_id="session-7",
            active=True,
            progress_excerpt="shard 3/12 still running",
        ),
    )

    assert result.record.status == "running"
    assert result.record.exit_status is None
    assert result.receipt == {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "job_id": "job-7",
        "status": "running",
        "reason": "stale_done_revived",
        "session_id": "session-7",
        "exit_status": None,
        "followup_status": "not_started",
        "followup_session_id": "",
        "duplicate_launch_refused": True,
        "completion_evidence_available": False,
        "corrective_action": (
            "Reattach to the live local job session and wait for explicit "
            "success marker or artifact evidence before completing."
        ),
    }


def test_live_session_reuse_refuses_duplicate_launch_for_running_job() -> None:
    result = reconcile_local_job_continuation(
        _record(status="pending"),
        live_evidence=LocalJobLiveEvidence(
            session_id="session-7",
            active=True,
            progress_excerpt="download 81%",
            exit_status=None,
        ),
    )

    assert result.record.status == "running"
    assert result.receipt["reason"] == "live_session_reused"
    assert result.receipt["duplicate_launch_refused"] is True
    assert result.receipt["corrective_action"] == (
        "Reuse the active local job session instead of launching duplicate work."
    )


def test_completed_record_requires_success_or_artifact_evidence() -> None:
    missing = reconcile_local_job_continuation(_record(status="completed", exit_status=0))
    marker = reconcile_local_job_continuation(
        _record(
            status="completed",
            exit_status=0,
            success_marker_path="/workspace/.runtime/jobs/job-7.success",
        )
    )
    artifact = reconcile_local_job_continuation(
        _record(
            status="completed",
            exit_status=0,
            artifact_paths=("/workspace/out/report.md",),
        )
    )

    assert missing.record.status == "blocked"
    assert missing.receipt["reason"] == "missing_completion_evidence"
    assert missing.receipt["completion_evidence_available"] is False
    assert marker.record.status == "completed"
    assert marker.receipt["reason"] == "completion_evidence_accepted"
    assert marker.receipt["completion_evidence_available"] is True
    assert artifact.receipt["reason"] == "completion_evidence_accepted"


def test_live_completion_evidence_accepts_completed_record() -> None:
    result = reconcile_local_job_continuation(
        _record(status="completed", exit_status=0),
        live_evidence=LocalJobLiveEvidence(
            session_id="session-7",
            active=False,
            progress_excerpt="done",
            artifact_paths=("/workspace/out/final.json",),
        ),
    )

    assert result.record.status == "completed"
    assert result.record.artifact_paths == ("/workspace/out/final.json",)
    assert result.receipt["reason"] == "completion_evidence_accepted"
    assert result.receipt["completion_evidence_available"] is True


def test_live_completion_evidence_is_normalized_before_persistence() -> None:
    result = reconcile_local_job_continuation(
        _record(
            status="completed",
            exit_status=0,
            success_marker_path=" /workspace/.runtime/jobs/job-7.success ",
            artifact_paths=(" /workspace/out/final.json ",),
        ),
        live_evidence=LocalJobLiveEvidence(
            session_id="session-7",
            active=False,
            progress_excerpt="done",
            artifact_paths=(
                "/workspace/out/final.json",
                " /workspace/out/summary.json ",
                " ",
            ),
        ),
    )

    assert result.record.status == "completed"
    assert result.record.success_marker_path == "/workspace/.runtime/jobs/job-7.success"
    assert result.record.artifact_paths == (
        "/workspace/out/final.json",
        "/workspace/out/summary.json",
    )
    assert result.receipt["reason"] == "completion_evidence_accepted"
    assert result.receipt["completion_evidence_available"] is True


def test_store_reconcile_persists_stale_done_self_heal_and_completion_evidence(
    tmp_path: Path,
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    stale_done = store.save_record(_record(status="completed", exit_status=0))

    revived = store.reconcile_record(
        stale_done.job_id,
        live_evidence=LocalJobLiveEvidence(
            session_id="session-7",
            active=True,
            progress_excerpt="shard 3/12 still running",
        ),
    )

    assert revived is not None
    assert revived.record.status == "running"
    assert revived.record.exit_status is None
    assert revived.record.revision == 1
    assert revived.receipt["reason"] == "stale_done_revived"
    assert store.load_record("job-7") == revived.record

    done_without_evidence = store.save_record(
        replace(revived.record, status="completed", exit_status=0),
        expected_revision=revived.record.revision,
    )
    blocked = store.reconcile_record(done_without_evidence.job_id)

    assert blocked is not None
    assert blocked.record.status == "blocked"
    assert blocked.record.revision == 3
    assert blocked.receipt["reason"] == "missing_completion_evidence"
    assert store.load_record("job-7") == blocked.record

    done_with_live_artifact = store.save_record(
        replace(blocked.record, status="completed", exit_status=0),
        expected_revision=blocked.record.revision,
    )
    accepted = store.reconcile_record(
        done_with_live_artifact.job_id,
        live_evidence=LocalJobLiveEvidence(
            session_id="session-7",
            active=False,
            progress_excerpt="completed",
            artifact_paths=("/workspace/out/final.json",),
        ),
    )

    assert accepted is not None
    assert accepted.record.status == "completed"
    assert accepted.record.artifact_paths == ("/workspace/out/final.json",)
    assert accepted.record.revision == 5
    assert accepted.receipt["reason"] == "completion_evidence_accepted"
    assert accepted.receipt["completion_evidence_available"] is True
    assert store.load_record("job-7") == accepted.record


def test_store_claim_followup_marks_completed_job_in_progress_once(tmp_path: Path) -> None:
    store = LocalJobContinuationStore(tmp_path)
    completed = store.save_record(
        _record(
            status="completed",
            exit_status=0,
            success_marker_path="/workspace/.runtime/jobs/job-7.success",
        )
    )

    claimed = store.claim_followup("job-7", followup_session_id=" followup-session-7 ")

    assert claimed is not None
    assert claimed.record == replace(
        completed,
        followup_status="in_progress",
        followup_session_id="followup-session-7",
        revision=1,
    )
    assert claimed.receipt["reason"] == "followup_claimed"
    assert claimed.receipt["followup_status"] == "in_progress"
    assert claimed.receipt["followup_session_id"] == "followup-session-7"
    assert claimed.receipt["completion_evidence_available"] is True
    assert store.load_record("job-7") == claimed.record

    duplicate = store.claim_followup("job-7", followup_session_id="other-followup")

    assert duplicate is not None
    assert duplicate.record == claimed.record
    assert duplicate.receipt["reason"] == "followup_already_claimed"
    assert duplicate.receipt["followup_session_id"] == "followup-session-7"
    assert store.load_record("job-7") == claimed.record


def test_store_claim_followup_emits_redacted_background_prompt_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_admissions: list[PromptContextAdmission] = []

    def capture_admit_background_continuation(**kwargs: Any) -> PromptContextAdmission:
        admission = original_admit_background_continuation(**kwargs)
        captured_admissions.append(admission)
        return admission

    monkeypatch.setattr(
        local_job_continuation_module,
        "admit_background_continuation",
        capture_admit_background_continuation,
    )

    store = LocalJobContinuationStore(tmp_path)
    store.save_record(
        _record(
            status="completed",
            exit_status=0,
            command=("melix", "bench", "--private-flag"),
            cwd="/workspace/private-project",
            log_path="/workspace/private-project/.runtime/jobs/job-7.log",
            session_id="session-secret-7",
            success_marker_path="/workspace/private-project/.runtime/jobs/job-7.success",
            artifact_paths=("/workspace/private-project/out/final.json",),
        )
    )

    claimed = store.claim_followup("job-7", followup_session_id="followup-session-7")

    assert claimed is not None
    assert claimed.receipt["reason"] == "followup_claimed"
    assert claimed.receipt["prompt_context_receipt_schema"] == (
        "melix.untrusted_context_receipt.v1"
    )
    assert claimed.receipt["prompt_context_receipt_count"] == 1
    assert claimed.receipt["prompt_context_receipts"] == [
        {
            "schema_version": "melix.untrusted_context_receipt.v1",
            "segment_id": "job-7:local-job-followup",
            "source_type": "background_continuation",
            "source_field": "local_job_followup",
            "source_id": "job-7",
            "message_role": "user",
            "trust_level": "untrusted",
            "policy": "data_only",
            "boundary_checked": True,
            "included": True,
            "owner_scope_checked": False,
            "reason": "local job follow-up is prompt data, not instructions",
            "corrective_action": (
                "Keep local job follow-up evidence in user-role prompt context."
            ),
        }
    ]
    assert len(captured_admissions) == 1
    assert captured_admissions[0].user_payload["local_job_followup"][
        "followup_status"
    ] == "in_progress"
    prompt_receipt_json = json.dumps(
        claimed.receipt["prompt_context_receipts"],
        ensure_ascii=False,
    )
    assert "--private-flag" not in prompt_receipt_json
    assert "/workspace/private-project" not in prompt_receipt_json
    assert "session-secret-7" not in prompt_receipt_json
    assert "final.json" not in prompt_receipt_json


def test_store_claim_followup_does_not_emit_prompt_receipt_for_duplicate_claim(
    tmp_path: Path,
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    store.save_record(
        _record(
            status="completed",
            exit_status=0,
            success_marker_path="/workspace/.runtime/jobs/job-7.success",
        )
    )
    claimed = store.claim_followup("job-7", followup_session_id="followup-session-7")

    duplicate = store.claim_followup("job-7", followup_session_id="other-followup")

    assert claimed is not None
    assert duplicate is not None
    assert claimed.receipt["prompt_context_receipt_count"] == 1
    assert "prompt_context_receipts" not in duplicate.receipt
    assert "prompt_context_receipt_count" not in duplicate.receipt


def test_store_claim_followup_blocks_completed_record_without_evidence(tmp_path: Path) -> None:
    store = LocalJobContinuationStore(tmp_path)
    completed = store.save_record(_record(status="completed", exit_status=0))

    blocked = store.claim_followup("job-7", followup_session_id="followup-session-7")

    assert blocked is not None
    assert blocked.record == replace(completed, status="blocked", revision=1)
    assert blocked.receipt["reason"] == "missing_completion_evidence"
    assert blocked.receipt["completion_evidence_available"] is False
    assert blocked.receipt["followup_status"] == "not_started"
    assert blocked.receipt["followup_session_id"] == ""
    assert store.load_record("job-7") == blocked.record


def test_store_claim_followup_persists_live_completion_evidence_before_claim(
    tmp_path: Path,
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    completed = store.save_record(_record(status="completed", exit_status=0))

    claimed = store.claim_followup(
        "job-7",
        followup_session_id="followup-session-7",
        live_evidence=LocalJobLiveEvidence(
            session_id="session-7",
            active=False,
            progress_excerpt="completed",
            artifact_paths=(" /workspace/out/final.json ",),
        ),
    )

    assert claimed is not None
    assert claimed.record == replace(
        completed,
        followup_status="in_progress",
        followup_session_id="followup-session-7",
        artifact_paths=("/workspace/out/final.json",),
        revision=1,
    )
    assert claimed.receipt["reason"] == "followup_claimed"
    assert claimed.receipt["completion_evidence_available"] is True
    assert store.load_record("job-7") == claimed.record


def test_store_claim_followup_prompt_context_admits_redacted_summary(
    tmp_path: Path,
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    completed = store.save_record(
        _record(
            status="completed",
            exit_status=0,
            artifact_paths=("/workspace/out/final.json",),
        )
    )

    claim = store.claim_followup_prompt_context(
        "job-7",
        followup_session_id="followup-session-7",
        completion_summary={
            "status": "completed",
            "summary": "Redacted completion summary.",
            "artifact_count": 1,
        },
        owner_scope_checked=True,
    )

    assert claim is not None
    assert claim.reconciliation.record == replace(
        completed,
        followup_status="in_progress",
        followup_session_id="followup-session-7",
        revision=1,
    )
    assert claim.reconciliation.receipt["reason"] == "followup_claimed"
    assert claim.prompt_context.user_payload == {
        "local_job_completion_summary": {
            "status": "completed",
            "summary": "Redacted completion summary.",
            "artifact_count": 1,
        }
    }
    assert claim.prompt_context.untrusted_context_receipt_count == 1
    receipt = claim.prompt_context.untrusted_context_receipts[0]
    assert receipt["schema_version"] == "melix.untrusted_context_receipt.v1"
    assert receipt["segment_id"] == "job-7:local-job-followup"
    assert receipt["source_type"] == "background_continuation"
    assert receipt["source_field"] == "local_job_completion_summary"
    assert receipt["source_id"] == "job-7"
    assert receipt["owner_scope_checked"] is True
    assert receipt["included"] is True
    assert receipt["reason"] == "local job completion summary is prompt data, not instructions"
    assert receipt["corrective_action"] == (
        "Keep local job completion summaries in user-role data context and do not "
        "project them into system or developer instructions."
    )
    assert "Redacted completion summary." not in json.dumps(receipt, sort_keys=True)
    assert store.load_record("job-7") == claim.reconciliation.record


@pytest.mark.parametrize(
    ("completion_summary", "owner_scope_checked", "source_field"),
    (
        ("not-a-dict", True, "local_job_completion_summary"),
        ({"status": "completed"}, "yes", "owner_scope_checked"),
    ),
)
def test_store_claim_followup_prompt_context_refuses_before_persisting_claim(
    tmp_path: Path,
    completion_summary: object,
    owner_scope_checked: object,
    source_field: str,
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    completed = store.save_record(
        _record(
            status="completed",
            exit_status=0,
            artifact_paths=("/workspace/out/final.json",),
        )
    )

    with pytest.raises(LocalJobContinuationAdmissionError) as exc_info:
        store.claim_followup_prompt_context(
            "job-7",
            followup_session_id="followup-session-7",
            completion_summary=completion_summary,  # type: ignore[arg-type]
            owner_scope_checked=owner_scope_checked,  # type: ignore[arg-type]
        )

    assert exc_info.value.reconciliation is not None
    assert exc_info.value.reconciliation.record == completed
    receipt = exc_info.value.refusal_receipts[0]
    assert receipt == {
        "schema_version": "melix.untrusted_context_receipt.v1",
        "segment_id": "job-7:local-job-followup",
        "source_type": "background_continuation",
        "source_field": source_field,
        "message_role": "user",
        "trust_level": "untrusted",
        "policy": "data_only",
        "boundary_checked": True,
        "included": False,
        "owner_scope_checked": owner_scope_checked if isinstance(owner_scope_checked, bool) else False,
        "reason": "invalid_background_continuation_field",
        "corrective_action": (
            "Reject malformed background continuation evidence before prompt assembly."
        ),
        "source_id": "job-7",
    }
    assert store.load_record("job-7") == completed


def test_store_claim_followup_prompt_context_returns_none_for_missing_record(
    tmp_path: Path,
) -> None:
    store = LocalJobContinuationStore(tmp_path)

    assert (
        store.claim_followup_prompt_context(
            "job-7",
            followup_session_id="followup-session-7",
            completion_summary={"status": "completed"},
            owner_scope_checked=True,
        )
        is None
    )


def test_store_claim_followup_prompt_context_preserves_store_blockers_without_payload(
    tmp_path: Path,
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    completed = store.save_record(_record(status="completed", exit_status=0))

    blocked = store.claim_followup_prompt_context(
        "job-7",
        followup_session_id="followup-session-7",
        completion_summary={"status": "completed"},
        owner_scope_checked=True,
    )

    assert blocked is not None
    assert blocked.reconciliation.record == replace(completed, status="blocked", revision=1)
    assert blocked.reconciliation.receipt["reason"] == "missing_completion_evidence"
    assert blocked.prompt_context.user_payload == {}
    assert blocked.prompt_context.untrusted_context_receipts == []
    assert store.load_record("job-7") == blocked.reconciliation.record


def test_store_claim_followup_prompt_context_skips_duplicate_claim_prompt_payload(
    tmp_path: Path,
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    completed = store.save_record(
        _record(
            status="completed",
            exit_status=0,
            artifact_paths=("/workspace/out/final.json",),
        )
    )
    claimed = store.save_record(
        replace(
            completed,
            followup_status="in_progress",
            followup_session_id="first-followup",
        ),
        expected_revision=completed.revision,
    )

    duplicate = store.claim_followup_prompt_context(
        "job-7",
        followup_session_id="second-followup",
        completion_summary={"status": "completed"},
        owner_scope_checked=True,
    )

    assert duplicate is not None
    assert duplicate.reconciliation.record == claimed
    assert duplicate.reconciliation.receipt["reason"] == "followup_already_claimed"
    assert duplicate.prompt_context.user_payload == {}
    assert duplicate.prompt_context.untrusted_context_receipts == []
    assert store.load_record("job-7") == claimed


def test_project_local_job_session_followup_returns_user_message_projection(
    tmp_path: Path,
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    completed = store.save_record(
        _record(
            status="completed",
            exit_status=0,
            command=("melix", "bench", "--private-flag"),
            cwd="/workspace/private-project",
            log_path="/workspace/private-project/.runtime/jobs/job-7.log",
            session_id="session-secret-7",
            success_marker_path="/workspace/private-project/.runtime/jobs/job-7.success",
            artifact_paths=("/workspace/private-project/out/final.json",),
        )
    )

    projection = project_local_job_session_followup(
        store,
        job_id="job-7",
        followup_session_id="followup-session-7",
        completion_summary={
            "status": "completed",
            "summary": "Redacted completion summary.",
            "artifact_count": 1,
        },
        owner_scope_checked=True,
    )

    assert projection is not None
    assert projection.claim.reconciliation.record == replace(
        completed,
        followup_status="in_progress",
        followup_session_id="followup-session-7",
        revision=1,
    )
    assert projection.claim_receipt["reason"] == "followup_claimed"
    assert projection.prompt_user_payload == {
        "local_job_completion_summary": {
            "status": "completed",
            "summary": "Redacted completion summary.",
            "artifact_count": 1,
        }
    }
    assert projection.untrusted_context_receipts == (
        projection.claim.prompt_context.untrusted_context_receipts
    )
    assert projection.followup_message == {
        "role": "user",
        "content": projection.prompt_user_payload,
        "untrusted_context_receipts": projection.untrusted_context_receipts,
    }
    receipt_json = json.dumps(projection.untrusted_context_receipts, sort_keys=True)
    assert "--private-flag" not in receipt_json
    assert "/workspace/private-project" not in receipt_json
    assert "session-secret-7" not in receipt_json
    assert "final.json" not in receipt_json
    assert "Redacted completion summary." not in receipt_json
    assert store.load_record("job-7") == projection.claim.reconciliation.record


def test_project_local_job_session_followup_preserves_store_blocker_without_message(
    tmp_path: Path,
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    completed = store.save_record(_record(status="completed", exit_status=0))

    projection = project_local_job_session_followup(
        store,
        job_id="job-7",
        followup_session_id="followup-session-7",
        completion_summary={"status": "completed"},
        owner_scope_checked=True,
    )

    assert projection is not None
    assert projection.claim.reconciliation.record == replace(completed, status="blocked", revision=1)
    assert projection.claim_receipt["reason"] == "missing_completion_evidence"
    assert projection.prompt_user_payload == {}
    assert projection.untrusted_context_receipts == []
    assert projection.followup_message is None
    assert store.load_record("job-7") == projection.claim.reconciliation.record


def test_project_local_job_session_followup_returns_none_for_missing_record(
    tmp_path: Path,
) -> None:
    store = LocalJobContinuationStore(tmp_path)

    assert (
        project_local_job_session_followup(
            store,
            job_id="job-7",
            followup_session_id="followup-session-7",
            completion_summary={"status": "completed"},
            owner_scope_checked=True,
        )
        is None
    )


def test_store_claim_followup_preserves_non_completed_records(tmp_path: Path) -> None:
    store = LocalJobContinuationStore(tmp_path)
    running = store.save_record(_record(status="running"))

    result = store.claim_followup("job-7", followup_session_id="followup-session-7")

    assert result is not None
    assert result.record == running
    assert result.receipt["reason"] == "followup_not_ready"
    assert result.receipt["followup_status"] == "not_started"
    assert store.load_record("job-7") == running


def test_store_scan_followup_candidates_reconciles_and_filters_ready_records(
    tmp_path: Path,
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    claimed = store.save_record(
        _record(
            job_id="claimed",
            status="completed",
            exit_status=0,
            artifact_paths=("/workspace/out/claimed.json",),
            followup_status="in_progress",
            followup_session_id="followup-claimed",
        )
    )
    live_done = store.save_record(
        _record(job_id="live-done", status="completed", exit_status=0)
    )
    missing = store.save_record(
        _record(job_id="missing", status="completed", exit_status=0)
    )
    ready = store.save_record(
        _record(
            job_id="ready",
            status="completed",
            exit_status=0,
            artifact_paths=("/workspace/out/ready.json",),
        )
    )
    running = store.save_record(_record(job_id="running", status="running"))
    stale = store.save_record(_record(job_id="stale", status="completed", exit_status=0))
    (tmp_path / "ready.json.lock").write_text(f"{os.getpid()}\n", encoding="utf-8")
    (tmp_path / "ready.json.tmp").write_text("{}", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not a record", encoding="utf-8")

    scan = store.scan_followup_candidates(
        live_evidence_by_job_id={
            "live-done": LocalJobLiveEvidence(
                session_id="session-7",
                active=False,
                progress_excerpt="done",
                artifact_paths=("/workspace/out/live-done.json",),
            ),
            "stale": LocalJobLiveEvidence(
                session_id="session-7",
                active=True,
                progress_excerpt="shard 3/12 still running",
            ),
        }
    )

    assert [candidate.record.job_id for candidate in scan.candidates] == [
        "live-done",
        "ready",
    ]
    assert [candidate.receipt["reason"] for candidate in scan.candidates] == [
        "followup_candidate_ready",
        "followup_candidate_ready",
    ]
    receipts_by_job = {receipt["job_id"]: receipt for receipt in scan.receipts}
    assert set(receipts_by_job) == {
        "claimed",
        "live-done",
        "missing",
        "ready",
        "running",
        "stale",
    }
    assert receipts_by_job["claimed"]["reason"] == "followup_already_claimed"
    assert receipts_by_job["claimed"]["followup_session_id"] == "followup-claimed"
    assert receipts_by_job["live-done"]["reason"] == "followup_candidate_ready"
    assert receipts_by_job["missing"]["reason"] == "missing_completion_evidence"
    assert receipts_by_job["ready"]["reason"] == "followup_candidate_ready"
    assert receipts_by_job["running"]["reason"] == "followup_not_ready"
    assert receipts_by_job["stale"]["reason"] == "stale_done_revived"
    assert store.load_record("claimed") == claimed
    assert store.load_record("live-done") == replace(
        live_done,
        artifact_paths=("/workspace/out/live-done.json",),
        revision=1,
    )
    assert store.load_record("missing") == replace(missing, status="blocked", revision=1)
    assert store.load_record("ready") == ready
    assert store.load_record("running") == running
    assert store.load_record("stale") == replace(
        stale,
        status="running",
        exit_status=None,
        revision=1,
    )


def test_store_scan_followup_candidates_returns_empty_for_missing_root(
    tmp_path: Path,
) -> None:
    scan = LocalJobContinuationStore(tmp_path / "missing").scan_followup_candidates()

    assert scan.candidates == ()
    assert scan.receipts == ()


def test_store_scan_followup_candidates_tolerates_record_deleted_during_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    store.save_record(
        _record(
            status="completed",
            exit_status=0,
            artifact_paths=("/workspace/out/ready.json",),
        )
    )
    original_load_record = store.load_record

    def delete_before_load(job_id: str) -> LocalJobContinuationRecord | None:
        if job_id == "job-7":
            (tmp_path / "job-7.json").unlink()
        return original_load_record(job_id)

    monkeypatch.setattr(store, "load_record", delete_before_load)

    scan = store.scan_followup_candidates()

    assert scan.candidates == ()
    assert scan.receipts == ()


def test_store_scan_followup_candidates_skips_unreadable_records(
    tmp_path: Path,
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    ready = store.save_record(
        _record(
            status="completed",
            exit_status=0,
            artifact_paths=("/workspace/out/ready.json",),
        )
    )
    (tmp_path / "corrupt.json").write_text("{", encoding="utf-8")
    (tmp_path / "metadata.json").write_text(
        json.dumps({"schema_version": "metadata.v1"}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "nested.json").mkdir()

    scan = store.scan_followup_candidates()

    assert [candidate.record.job_id for candidate in scan.candidates] == ["job-7"]
    receipts_by_job = {receipt["job_id"]: receipt for receipt in scan.receipts}
    assert receipts_by_job["job-7"]["reason"] == "followup_candidate_ready"
    assert receipts_by_job["corrupt"]["reason"] == "record_unreadable"
    assert receipts_by_job["metadata"]["reason"] == "record_unreadable"
    assert "nested" not in receipts_by_job
    assert store.load_record("job-7") == ready


def test_store_scan_followup_candidates_preserves_store_error_receipts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    ready = store.save_record(
        _record(
            job_id="ready",
            status="completed",
            exit_status=0,
            artifact_paths=("/workspace/out/ready.json",),
        )
    )
    stale_done = store.save_record(
        _record(job_id="stale", status="completed", exit_status=0)
    )
    original_save_record = store.save_record
    injected_race = False

    def race_before_reconcile_write(
        record: LocalJobContinuationRecord,
        *,
        expected_revision: int | None = None,
    ) -> LocalJobContinuationRecord:
        nonlocal injected_race
        if record.job_id == "stale" and not injected_race and expected_revision == stale_done.revision:
            injected_race = True
            original_save_record(
                replace(stale_done, status="running", exit_status=None),
                expected_revision=stale_done.revision,
            )
        return original_save_record(record, expected_revision=expected_revision)

    monkeypatch.setattr(store, "save_record", race_before_reconcile_write)

    scan = store.scan_followup_candidates(
        live_evidence_by_job_id={
            "stale": LocalJobLiveEvidence(
                session_id="session-7",
                active=True,
                progress_excerpt="shard 3/12 still running",
            ),
        }
    )

    assert [candidate.record.job_id for candidate in scan.candidates] == ["ready"]
    receipts_by_job = {receipt["job_id"]: receipt for receipt in scan.receipts}
    assert receipts_by_job["ready"]["reason"] == "followup_candidate_ready"
    assert receipts_by_job["stale"]["reason"] == "record_revision_mismatch"
    assert store.load_record("ready") == ready
    assert store.load_record("stale") == replace(
        stale_done,
        status="running",
        exit_status=None,
        revision=1,
    )


def test_store_claim_scanned_followups_claims_ready_prompt_contexts_once(
    tmp_path: Path,
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    ready = store.save_record(
        _record(
            job_id="ready",
            status="completed",
            exit_status=0,
            artifact_paths=("/workspace/out/ready.json",),
        )
    )
    live_done = store.save_record(
        _record(job_id="live-done", status="completed", exit_status=0)
    )
    claimed = store.save_record(
        _record(
            job_id="claimed",
            status="completed",
            exit_status=0,
            artifact_paths=("/workspace/out/claimed.json",),
            followup_status="in_progress",
            followup_session_id="existing-followup",
        )
    )
    blocked = store.save_record(_record(job_id="blocked", status="completed", exit_status=0))

    batch = store.claim_scanned_followup_prompt_contexts(
        followup_session_ids_by_job_id={
            "ready": "followup-ready",
            "live-done": "followup-live",
        },
        completion_summaries_by_job_id={
            "ready": {"status": "completed", "summary": "Ready summary."},
            "live-done": {"status": "completed", "summary": "Live summary."},
        },
        owner_scope_checked_by_job_id={
            "ready": True,
            "live-done": False,
        },
        live_evidence_by_job_id={
            "live-done": LocalJobLiveEvidence(
                session_id="session-7",
                active=False,
                progress_excerpt="done",
                artifact_paths=("/workspace/out/live-done.json",),
            ),
        },
    )

    assert [claim.reconciliation.record.job_id for claim in batch.claims] == [
        "live-done",
        "ready",
    ]
    assert [claim.reconciliation.receipt["reason"] for claim in batch.claims] == [
        "followup_claimed",
        "followup_claimed",
    ]
    assert [claim.prompt_context.user_payload for claim in batch.claims] == [
        {"local_job_completion_summary": {"status": "completed", "summary": "Live summary."}},
        {"local_job_completion_summary": {"status": "completed", "summary": "Ready summary."}},
    ]
    receipts_by_job = {receipt["job_id"]: receipt for receipt in batch.receipts}
    assert receipts_by_job["claimed"]["reason"] == "followup_already_claimed"
    assert receipts_by_job["blocked"]["reason"] == "missing_completion_evidence"
    assert receipts_by_job["live-done"]["reason"] == "followup_claimed"
    assert receipts_by_job["live-done"]["followup_session_id"] == "followup-live"
    assert receipts_by_job["ready"]["reason"] == "followup_claimed"
    assert receipts_by_job["ready"]["followup_session_id"] == "followup-ready"
    assert batch.refusal_receipts == ()
    assert store.load_record("ready") == replace(
        ready,
        followup_status="in_progress",
        followup_session_id="followup-ready",
        revision=1,
    )
    assert store.load_record("live-done") == replace(
        live_done,
        artifact_paths=("/workspace/out/live-done.json",),
        followup_status="in_progress",
        followup_session_id="followup-live",
        revision=2,
    )
    assert store.load_record("claimed") == claimed
    assert store.load_record("blocked") == replace(blocked, status="blocked", revision=1)


def test_store_claim_scanned_followups_reports_missing_claim_inputs(
    tmp_path: Path,
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    ready = store.save_record(
        _record(
            status="completed",
            exit_status=0,
            artifact_paths=("/workspace/out/ready.json",),
        )
    )

    batch = store.claim_scanned_followup_prompt_contexts(
        followup_session_ids_by_job_id={},
        completion_summaries_by_job_id={},
        owner_scope_checked_by_job_id={},
    )

    assert batch.claims == ()
    assert batch.refusal_receipts == ()
    assert [receipt["reason"] for receipt in batch.receipts] == [
        "followup_candidate_ready",
        "followup_claim_input_missing",
    ]
    assert batch.receipts[1]["job_id"] == "job-7"
    assert batch.receipts[1]["followup_status"] == "not_started"
    assert store.load_record("job-7") == ready


def test_store_claim_scanned_followups_normalizes_none_claim_inputs(
    tmp_path: Path,
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    ready = store.save_record(
        _record(
            status="completed",
            exit_status=0,
            artifact_paths=("/workspace/out/ready.json",),
        )
    )

    batch = store.claim_scanned_followup_prompt_contexts(
        followup_session_ids_by_job_id=None,
        completion_summaries_by_job_id=None,
        owner_scope_checked_by_job_id=None,
    )

    assert batch.claims == ()
    assert batch.refusal_receipts == ()
    assert [receipt["reason"] for receipt in batch.receipts] == [
        "followup_candidate_ready",
        "followup_claim_input_missing",
    ]
    assert batch.receipts[1]["missing_fields"] == [
        "followup_session_id",
        "completion_summary",
        "owner_scope_checked",
    ]
    assert store.load_record("job-7") == ready


def test_store_claim_scanned_followups_preserves_admission_refusal_without_claim(
    tmp_path: Path,
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    ready = store.save_record(
        _record(
            status="completed",
            exit_status=0,
            artifact_paths=("/workspace/out/ready.json",),
        )
    )

    batch = store.claim_scanned_followup_prompt_contexts(
        followup_session_ids_by_job_id={"job-7": "followup-session-7"},
        completion_summaries_by_job_id={"job-7": "not-a-dict"},
        owner_scope_checked_by_job_id={"job-7": True},
    )

    assert batch.claims == ()
    assert [receipt["reason"] for receipt in batch.receipts] == [
        "followup_candidate_ready",
        "followup_prompt_context_refused",
    ]
    assert len(batch.refusal_receipts) == 1
    assert batch.refusal_receipts[0]["source_field"] == "local_job_completion_summary"
    assert batch.refusal_receipts[0]["included"] is False
    assert store.load_record("job-7") == ready


def test_store_claim_scanned_followups_records_admission_refusal_without_reconciliation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    ready = store.save_record(
        _record(
            status="completed",
            exit_status=0,
            artifact_paths=("/workspace/out/ready.json",),
        )
    )
    refusal_receipt = {"included": False, "source_field": "local_job_completion_summary"}

    def refuse_without_reconciliation(
        job_id: str,
        *,
        followup_session_id: str,
        completion_summary: dict[str, Any],
        owner_scope_checked: bool,
        live_evidence: LocalJobLiveEvidence | None = None,
    ) -> object:
        raise LocalJobContinuationAdmissionError(
            "prompt context refused",
            reconciliation=None,
            refusal_receipts=[refusal_receipt],
        )

    monkeypatch.setattr(store, "claim_followup_prompt_context", refuse_without_reconciliation)

    batch = store.claim_scanned_followup_prompt_contexts(
        followup_session_ids_by_job_id={"job-7": "followup-session-7"},
        completion_summaries_by_job_id={"job-7": {"status": "completed"}},
        owner_scope_checked_by_job_id={"job-7": True},
    )

    assert batch.claims == ()
    assert [receipt["reason"] for receipt in batch.receipts] == [
        "followup_candidate_ready",
        "followup_prompt_context_refused",
    ]
    assert batch.receipts[1]["job_id"] == "job-7"
    assert batch.refusal_receipts == (refusal_receipt,)
    assert store.load_record("job-7") == ready


def test_store_claim_scanned_followups_reports_invalid_claim_inputs(
    tmp_path: Path,
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    ready = store.save_record(
        _record(
            status="completed",
            exit_status=0,
            artifact_paths=("/workspace/out/ready.json",),
        )
    )

    batch = store.claim_scanned_followup_prompt_contexts(
        followup_session_ids_by_job_id={"job-7": " "},
        completion_summaries_by_job_id={"job-7": {"status": "completed"}},
        owner_scope_checked_by_job_id={"job-7": True},
    )

    assert batch.claims == ()
    assert batch.refusal_receipts == ()
    assert [receipt["reason"] for receipt in batch.receipts] == [
        "followup_candidate_ready",
        "followup_claim_input_invalid",
    ]
    assert batch.receipts[1]["input_error"] == "followup_session_id must be a non-empty string"
    assert store.load_record("job-7") == ready


def test_store_claim_scanned_followups_reports_record_deleted_before_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    ready = store.save_record(
        _record(
            status="completed",
            exit_status=0,
            artifact_paths=("/workspace/out/ready.json",),
        )
    )
    original_claim = store.claim_followup_prompt_context

    def delete_before_claim(
        job_id: str,
        *,
        followup_session_id: str,
        completion_summary: dict[str, Any],
        owner_scope_checked: bool,
        live_evidence: LocalJobLiveEvidence | None = None,
    ) -> object:
        (tmp_path / f"{job_id}.json").unlink()
        return original_claim(
            job_id,
            followup_session_id=followup_session_id,
            completion_summary=completion_summary,
            owner_scope_checked=owner_scope_checked,
            live_evidence=live_evidence,
        )

    monkeypatch.setattr(store, "claim_followup_prompt_context", delete_before_claim)

    batch = store.claim_scanned_followup_prompt_contexts(
        followup_session_ids_by_job_id={"job-7": "followup-session-7"},
        completion_summaries_by_job_id={"job-7": {"status": "completed"}},
        owner_scope_checked_by_job_id={"job-7": True},
    )

    assert batch.claims == ()
    assert batch.refusal_receipts == ()
    assert [receipt["reason"] for receipt in batch.receipts] == [
        "followup_candidate_ready",
        "followup_record_missing",
    ]
    assert batch.receipts[1]["job_id"] == ready.job_id
    assert store.load_record("job-7") is None


def test_store_claim_scanned_followups_isolates_claim_revision_races(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    raced = store.save_record(
        _record(
            job_id="raced",
            status="completed",
            exit_status=0,
            artifact_paths=("/workspace/out/raced.json",),
        )
    )
    ready = store.save_record(
        _record(
            job_id="ready",
            status="completed",
            exit_status=0,
            artifact_paths=("/workspace/out/ready.json",),
        )
    )
    original_save_record = store.save_record
    injected_race = False

    def race_before_claim_write(
        record: LocalJobContinuationRecord,
        *,
        expected_revision: int | None = None,
    ) -> LocalJobContinuationRecord:
        nonlocal injected_race
        if record.job_id == "raced" and not injected_race and expected_revision == raced.revision:
            injected_race = True
            original_save_record(
                replace(
                    raced,
                    followup_status="in_progress",
                    followup_session_id="other-followup",
                ),
                expected_revision=raced.revision,
            )
        return original_save_record(record, expected_revision=expected_revision)

    monkeypatch.setattr(store, "save_record", race_before_claim_write)

    batch = store.claim_scanned_followup_prompt_contexts(
        followup_session_ids_by_job_id={
            "raced": "followup-raced",
            "ready": "followup-ready",
        },
        completion_summaries_by_job_id={
            "raced": {"status": "completed", "summary": "Raced summary."},
            "ready": {"status": "completed", "summary": "Ready summary."},
        },
        owner_scope_checked_by_job_id={
            "raced": True,
            "ready": True,
        },
    )

    assert [claim.reconciliation.record.job_id for claim in batch.claims] == ["ready"]
    receipts_by_reason = [receipt["reason"] for receipt in batch.receipts]
    assert receipts_by_reason == [
        "followup_candidate_ready",
        "followup_candidate_ready",
        "record_revision_mismatch",
        "followup_claimed",
    ]
    assert store.load_record("raced") == replace(
        raced,
        followup_status="in_progress",
        followup_session_id="other-followup",
        revision=1,
    )
    assert store.load_record("ready") == replace(
        ready,
        followup_status="in_progress",
        followup_session_id="followup-ready",
        revision=1,
    )


def test_store_claim_followup_uses_revision_guard_for_concurrent_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    completed = store.save_record(
        _record(
            status="completed",
            exit_status=0,
            artifact_paths=("/workspace/out/final.json",),
        )
    )
    original_save_record = store.save_record
    injected_race = False

    def race_before_claim_write(
        record: LocalJobContinuationRecord,
        *,
        expected_revision: int | None = None,
    ) -> LocalJobContinuationRecord:
        nonlocal injected_race
        if not injected_race and expected_revision == completed.revision:
            injected_race = True
            original_save_record(
                replace(
                    completed,
                    followup_status="in_progress",
                    followup_session_id="other-followup",
                ),
                expected_revision=completed.revision,
            )
        return original_save_record(record, expected_revision=expected_revision)

    monkeypatch.setattr(store, "save_record", race_before_claim_write)

    with pytest.raises(LocalJobContinuationStoreError) as exc_info:
        store.claim_followup("job-7", followup_session_id="followup-session-7")

    assert exc_info.value.receipt["reason"] == "record_revision_mismatch"
    assert store.load_record("job-7") == replace(
        completed,
        followup_status="in_progress",
        followup_session_id="other-followup",
        revision=1,
    )


def test_store_reconcile_returns_none_for_missing_record(tmp_path: Path) -> None:
    store = LocalJobContinuationStore(tmp_path)

    assert store.reconcile_record("job-7") is None


def test_store_reconcile_uses_revision_guard_for_concurrent_updates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    stale_done = store.save_record(_record(status="completed", exit_status=0))
    original_save_record = store.save_record
    injected_race = False

    def race_before_reconcile_write(
        record: LocalJobContinuationRecord,
        *,
        expected_revision: int | None = None,
    ) -> LocalJobContinuationRecord:
        nonlocal injected_race
        if not injected_race and expected_revision == stale_done.revision:
            injected_race = True
            original_save_record(
                replace(stale_done, status="running", exit_status=None),
                expected_revision=stale_done.revision,
            )
        return original_save_record(record, expected_revision=expected_revision)

    monkeypatch.setattr(store, "save_record", race_before_reconcile_write)

    with pytest.raises(LocalJobContinuationStoreError) as exc_info:
        store.reconcile_record(
            stale_done.job_id,
            live_evidence=LocalJobLiveEvidence(
                session_id="session-7",
                active=True,
                progress_excerpt="shard 3/12 still running",
            ),
        )

    assert exc_info.value.receipt["reason"] == "record_revision_mismatch"
    assert store.load_record("job-7") == replace(
        stale_done,
        status="running",
        exit_status=None,
        revision=1,
    )


def test_non_completed_record_without_matching_live_evidence_is_preserved() -> None:
    result = reconcile_local_job_continuation(
        _record(
            status="failed",
            exit_status=2,
            success_marker_path="/workspace/.runtime/jobs/job-7.success",
        ),
        live_evidence=LocalJobLiveEvidence(
            session_id="other-session",
            active=True,
            progress_excerpt="unrelated progress",
        ),
    )

    assert result.record.status == "failed"
    assert result.record.exit_status == 2
    assert result.receipt["reason"] == "record_state_preserved"
    assert result.receipt["completion_evidence_available"] is True
    assert result.receipt["duplicate_launch_refused"] is False


def test_store_revision_guard_rejects_concurrent_stale_update(tmp_path: Path) -> None:
    store = LocalJobContinuationStore(tmp_path)
    first = store.save_record(_record(status="pending"))
    second = store.save_record(_record(status="running"), expected_revision=first.revision)

    with pytest.raises(LocalJobContinuationStoreError) as exc_info:
        store.save_record(_record(status="completed", exit_status=0), expected_revision=first.revision)

    assert second.revision == 1
    assert exc_info.value.receipt["schema_version"] == RECEIPT_SCHEMA_VERSION
    assert exc_info.value.receipt["reason"] == "record_revision_mismatch"
    assert store.load_record("job-7") == second


def test_load_record_tolerates_record_deleted_between_path_resolution_and_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    saved = store.save_record(_record(status="running"))
    original_read_text = Path.read_text

    def delete_before_read(path: Path, *args: object, **kwargs: object) -> str:
        if path == tmp_path / "job-7.json":
            path.unlink()
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", delete_before_read)

    assert store.load_record(saved.job_id) is None


def test_store_lock_guard_rejects_active_writer(tmp_path: Path) -> None:
    store = LocalJobContinuationStore(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    lock_path = tmp_path / "job-7.json.lock"
    lock_path.write_text(f"{os.getpid()}\n", encoding="utf-8")

    try:
        with pytest.raises(LocalJobContinuationStoreError) as exc_info:
            store.save_record(_record(status="running"))
    finally:
        lock_path.unlink(missing_ok=True)

    assert exc_info.value.receipt == {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "job_id": "job-7",
        "status": "blocked",
        "reason": "record_write_locked",
        "session_id": "",
        "exit_status": None,
        "followup_status": "blocked",
        "followup_session_id": "",
        "duplicate_launch_refused": False,
        "completion_evidence_available": False,
        "corrective_action": "Retry after the active local job record writer finishes.",
    }


def test_store_lock_guard_preserves_unparseable_lock_file(tmp_path: Path) -> None:
    store = LocalJobContinuationStore(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    lock_path = tmp_path / "job-7.json.lock"
    lock_path.write_text("other-writer\n", encoding="utf-8")

    try:
        with pytest.raises(LocalJobContinuationStoreError) as exc_info:
            store.save_record(_record(status="running"))
    finally:
        lock_path.unlink(missing_ok=True)

    assert exc_info.value.receipt["reason"] == "record_write_locked"


def test_store_recovers_stale_lock_for_dead_writer_pid(tmp_path: Path) -> None:
    store = LocalJobContinuationStore(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    lock_path = tmp_path / "job-7.json.lock"
    lock_path.write_text("999999\n", encoding="utf-8")

    saved = store.save_record(_record(status="running"))

    assert saved.revision == 0
    assert store.load_record("job-7") == saved
    assert not lock_path.exists()


def test_record_lock_cleanup_failure_is_non_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    lock_path = tmp_path / "job-7.json.lock"
    original_unlink = Path.unlink

    def fail_lock_cleanup(path: Path, *args: object, **kwargs: object) -> None:
        if path == lock_path:
            raise OSError("cleanup denied")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_lock_cleanup)

    saved = store.save_record(_record(status="running"))

    assert saved.status == "running"
    monkeypatch.undo()
    lock_path.unlink(missing_ok=True)


def test_stale_lock_cleanup_tolerates_concurrent_lock_removal(tmp_path: Path) -> None:
    store = LocalJobContinuationStore(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    lock_path = tmp_path / "job-7.json.lock"
    lock_path.write_text("999999\n", encoding="utf-8")
    original_rename = os.rename

    def remove_before_rename(src: Path | str, dst: Path | str) -> None:
        if Path(src) == lock_path and lock_path.exists():
            lock_path.unlink()
            raise FileNotFoundError(src)
        original_rename(src, dst)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(os, "rename", remove_before_rename)
        saved = store.save_record(_record(status="running"))

    assert saved.status == "running"
    assert not lock_path.exists()


def test_stale_lock_cleanup_retries_when_lock_disappears_before_pid_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    lock_path = tmp_path / "job-7.json.lock"
    lock_path.write_text("999999\n", encoding="utf-8")
    original_read_text = Path.read_text

    def remove_before_pid_read(path: Path, *args: object, **kwargs: object) -> str:
        if path == lock_path and lock_path.exists():
            lock_path.unlink()
            raise FileNotFoundError(path)
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", remove_before_pid_read)

    saved = store.save_record(_record(status="running"))

    assert saved.status == "running"
    assert not lock_path.exists()


def test_stale_lock_recovery_blocks_when_guard_is_active(tmp_path: Path) -> None:
    store = LocalJobContinuationStore(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    lock_path = tmp_path / "job-7.json.lock"
    guard_path = tmp_path / "job-7.json.lock.recovery"
    lock_path.write_text("999999\n", encoding="utf-8")
    guard_path.write_text(f"{os.getpid()}\n", encoding="utf-8")

    try:
        with pytest.raises(LocalJobContinuationStoreError) as exc_info:
            store.save_record(_record(status="running"))
    finally:
        lock_path.unlink(missing_ok=True)
        guard_path.unlink(missing_ok=True)

    assert exc_info.value.receipt["reason"] == "record_write_locked"


def test_stale_lock_recovery_reclaims_dead_recovery_guard(tmp_path: Path) -> None:
    store = LocalJobContinuationStore(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    lock_path = tmp_path / "job-7.json.lock"
    guard_path = tmp_path / "job-7.json.lock.recovery"
    lock_path.write_text("999999\n", encoding="utf-8")
    guard_path.write_text("999998\n", encoding="utf-8")

    saved = store.save_record(_record(status="running"))

    assert saved.status == "running"
    assert not guard_path.exists()


def test_stale_lock_recovery_blocks_when_recovery_guard_reacquired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    guard_path = tmp_path / "job-7.json.lock.recovery"
    tmp_path.mkdir(parents=True, exist_ok=True)
    guard_path.write_text("999998\n", encoding="utf-8")
    original_open = os.open

    def race_reacquire_guard(path: Path | str, flags: int, mode: int = 0o777) -> int:
        if Path(path) == guard_path and not guard_path.exists():
            raise FileExistsError(path)
        return original_open(path, flags, mode)

    monkeypatch.setattr(os, "open", race_reacquire_guard)

    assert store._open_record_lock_recovery_guard(guard_path) is None


def test_stale_lock_recovery_blocks_when_lock_rename_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    lock_path = tmp_path / "job-7.json.lock"
    lock_path.write_text("999999\n", encoding="utf-8")

    def fail_rename(src: Path | str, dst: Path | str) -> None:
        if Path(src) == lock_path:
            raise OSError("rename denied")
        os.rename(src, dst)

    monkeypatch.setattr(os, "rename", fail_rename)

    with pytest.raises(LocalJobContinuationStoreError) as exc_info:
        store.save_record(_record(status="running"))

    assert exc_info.value.receipt["reason"] == "record_write_locked"
    assert lock_path.read_text(encoding="utf-8") == "999999\n"


def test_stale_lock_recovery_restores_lock_when_renamed_pid_is_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    lock_path = tmp_path / "job-7.json.lock"
    lock_path.write_text("999999\n", encoding="utf-8")
    original_rename = os.rename

    def corrupt_temp_after_rename(src: Path | str, dst: Path | str) -> None:
        original_rename(src, dst)
        if Path(src) == lock_path:
            Path(dst).write_text("not-a-pid\n", encoding="utf-8")

    monkeypatch.setattr(os, "rename", corrupt_temp_after_rename)

    with pytest.raises(LocalJobContinuationStoreError) as exc_info:
        store.save_record(_record(status="running"))

    assert exc_info.value.receipt["reason"] == "record_write_locked"
    assert lock_path.read_text(encoding="utf-8") == "not-a-pid\n"


def test_stale_lock_recovery_preserves_new_lock_acquired_after_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    lock_path = tmp_path / "job-7.json.lock"
    lock_path.write_text("999999\n", encoding="utf-8")
    original_unlink = Path.unlink

    def acquire_new_lock_before_stale_temp_unlink(
        path: Path, *args: object, **kwargs: object
    ) -> None:
        if path.name.startswith(f"{lock_path.name}.stale."):
            lock_path.write_text(f"{os.getpid()}\n", encoding="utf-8")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", acquire_new_lock_before_stale_temp_unlink)

    with pytest.raises(LocalJobContinuationStoreError) as exc_info:
        store.save_record(_record(status="running"))

    assert exc_info.value.receipt["reason"] == "record_write_locked"
    assert lock_path.read_text(encoding="utf-8") == f"{os.getpid()}\n"


def test_stale_lock_recovery_restores_lock_when_renamed_pid_is_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    lock_path = tmp_path / "job-7.json.lock"
    lock_path.write_text("999999\n", encoding="utf-8")
    original_rename = os.rename

    def rewrite_temp_to_active_pid(src: Path | str, dst: Path | str) -> None:
        original_rename(src, dst)
        if Path(src) == lock_path:
            Path(dst).write_text(f"{os.getpid()}\n", encoding="utf-8")

    monkeypatch.setattr(os, "rename", rewrite_temp_to_active_pid)

    with pytest.raises(LocalJobContinuationStoreError) as exc_info:
        store.save_record(_record(status="running"))

    assert exc_info.value.receipt["reason"] == "record_write_locked"
    assert lock_path.read_text(encoding="utf-8") == f"{os.getpid()}\n"


def test_stale_lock_recovery_tolerates_temp_removed_before_unlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    lock_path = tmp_path / "job-7.json.lock"
    lock_path.write_text("999999\n", encoding="utf-8")
    original_unlink = Path.unlink

    def remove_temp_before_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path.name.startswith(f"{lock_path.name}.stale."):
            original_unlink(path)
            raise FileNotFoundError(path)
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", remove_temp_before_unlink)

    saved = store.save_record(_record(status="running"))

    assert saved.status == "running"
    assert not lock_path.exists()


def test_stale_lock_cleanup_preserves_lock_when_unlink_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    lock_path = tmp_path / "job-7.json.lock"
    lock_path.write_text("999999\n", encoding="utf-8")
    original_unlink = Path.unlink

    def fail_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path.name.startswith(f"{lock_path.name}.stale."):
            raise OSError("permission denied")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_unlink)

    with pytest.raises(LocalJobContinuationStoreError) as exc_info:
        store.save_record(_record(status="running"))

    assert exc_info.value.receipt["reason"] == "record_write_locked"
    assert lock_path.read_text(encoding="utf-8") == "999999\n"


def test_stale_lock_recovery_tolerates_recovery_guard_cleanup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    lock_path = tmp_path / "job-7.json.lock"
    guard_path = tmp_path / "job-7.json.lock.recovery"
    lock_path.write_text("999999\n", encoding="utf-8")
    original_unlink = Path.unlink

    def fail_guard_cleanup(path: Path, *args: object, **kwargs: object) -> None:
        if path == guard_path:
            raise OSError("guard cleanup denied")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_guard_cleanup)

    saved = store.save_record(_record(status="running"))

    assert saved.status == "running"
    monkeypatch.undo()
    guard_path.unlink(missing_ok=True)


def test_recovery_guard_refuses_unparseable_and_active_pids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    guard_path = tmp_path / "job-7.json.lock.recovery"
    tmp_path.mkdir(parents=True, exist_ok=True)
    guard_path.write_text("not-a-pid\n", encoding="utf-8")

    assert store._remove_stale_record_lock_recovery_guard(guard_path) is False

    guard_path.write_text("42\n", encoding="utf-8")

    def deny_signal(pid: int, signal: int) -> None:
        raise PermissionError("not owned")

    monkeypatch.setattr(os, "kill", deny_signal)

    assert store._remove_stale_record_lock_recovery_guard(guard_path) is False


def test_recovery_guard_cleanup_handles_missing_and_failed_unlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    guard_path = tmp_path / "job-7.json.lock.recovery"
    tmp_path.mkdir(parents=True, exist_ok=True)
    guard_path.write_text("999998\n", encoding="utf-8")
    original_unlink = Path.unlink

    def remove_before_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path == guard_path:
            original_unlink(path)
            raise FileNotFoundError(path)
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", remove_before_unlink)

    assert store._remove_stale_record_lock_recovery_guard(guard_path) is True

    monkeypatch.undo()
    guard_path.write_text("999998\n", encoding="utf-8")

    def fail_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path == guard_path:
            raise OSError("cleanup denied")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_unlink)

    assert store._remove_stale_record_lock_recovery_guard(guard_path) is False


def test_restore_renamed_lock_handles_restore_races(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    lock_path = tmp_path / "job-7.json.lock"
    temp_path = tmp_path / "job-7.json.lock.stale.test"
    tmp_path.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(f"{os.getpid()}\n", encoding="utf-8")
    temp_path.write_text("999998\n", encoding="utf-8")

    store._restore_renamed_record_lock(temp_path, lock_path)

    assert lock_path.read_text(encoding="utf-8") == f"{os.getpid()}\n"
    assert not temp_path.exists()

    temp_path.write_text("999998\n", encoding="utf-8")

    def fail_link(src: Path | str, dst: Path | str) -> None:
        raise OSError("link denied")

    monkeypatch.setattr(os, "link", fail_link)

    store._restore_renamed_record_lock(temp_path, lock_path)

    assert temp_path.exists()

    monkeypatch.undo()
    lock_path.unlink()
    original_unlink = Path.unlink

    def fail_temp_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path == temp_path:
            raise OSError("unlink denied")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_temp_unlink)

    store._restore_renamed_record_lock(temp_path, lock_path)

    assert lock_path.read_text(encoding="utf-8") == "999998\n"


def test_lock_cleanup_treats_permission_errors_as_active_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    lock_path = tmp_path / "job-7.json.lock"
    lock_path.write_text("42\n", encoding="utf-8")

    def deny_signal(pid: int, signal: int) -> None:
        raise PermissionError("not owned")

    monkeypatch.setattr(os, "kill", deny_signal)

    with pytest.raises(LocalJobContinuationStoreError) as exc_info:
        store.save_record(_record(status="running"))

    assert exc_info.value.receipt["reason"] == "record_write_locked"


def test_lock_cleanup_treats_eperm_oserror_as_active_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    lock_path = tmp_path / "job-7.json.lock"
    lock_path.write_text("42\n", encoding="utf-8")

    def deny_signal(pid: int, signal: int) -> None:
        error = OSError("not owned")
        error.errno = 1
        raise error

    monkeypatch.setattr(os, "kill", deny_signal)

    with pytest.raises(LocalJobContinuationStoreError) as exc_info:
        store.save_record(_record(status="running"))

    assert exc_info.value.receipt["reason"] == "record_write_locked"


def test_lock_cleanup_treats_signal_value_error_as_active_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    lock_path = tmp_path / "job-7.json.lock"
    lock_path.write_text("42\n", encoding="utf-8")

    def reject_signal(pid: int, signal: int) -> None:
        raise ValueError("unsupported signal")

    monkeypatch.setattr(os, "kill", reject_signal)

    with pytest.raises(LocalJobContinuationStoreError) as exc_info:
        store.save_record(_record(status="running"))

    assert exc_info.value.receipt["reason"] == "record_write_locked"


def test_lock_cleanup_treats_windows_process_ids_as_active_without_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalJobContinuationStore(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    lock_path = tmp_path / "job-7.json.lock"
    lock_path.write_text("999999\n", encoding="utf-8")

    def fail_if_signalled(pid: int, signal: int) -> None:
        raise AssertionError("os.kill(pid, 0) must not run on Windows")

    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(os, "kill", fail_if_signalled)

    with pytest.raises(LocalJobContinuationStoreError) as exc_info:
        store.save_record(_record(status="running"))

    assert exc_info.value.receipt["reason"] == "record_write_locked"
    assert lock_path.read_text(encoding="utf-8") == "999999\n"


def test_with_revision_rejects_negative_revision() -> None:
    with pytest.raises(ValueError, match="revision must be non-negative"):
        _record().with_revision(-1)


def test_with_revision_rejects_null_revision() -> None:
    with pytest.raises(ValueError, match="revision must be an integer"):
        _record().with_revision(None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "job_id",
    (
        "bad:name",
        "bad*name",
        "bad?name",
        'bad"name',
        "bad<name",
        "bad>name",
        "bad|name",
        "bad\x00name",
        "bad\nname",
    ),
)
def test_record_validation_rejects_cross_platform_unsafe_job_ids(job_id: str) -> None:
    with pytest.raises(ValueError):
        _record(job_id=job_id).to_dict()


@pytest.mark.parametrize(
    "payload",
    (
        {"schema_version": "old", "job_id": "job-7"},
        {
            "schema_version": RECORD_SCHEMA_VERSION,
            "job_id": "../job-7",
            "command": ["melix"],
            "cwd": "/workspace",
            "log_path": "/tmp/job.log",
            "session_id": "session-7",
            "status": "pending",
            "followup_status": "not_started",
        },
        {
            "schema_version": RECORD_SCHEMA_VERSION,
            "job_id": "job-7",
            "command": ["melix", 7],
            "cwd": "/workspace",
            "log_path": "/tmp/job.log",
            "session_id": "session-7",
            "status": "pending",
            "followup_status": "not_started",
        },
        {
            "schema_version": RECORD_SCHEMA_VERSION,
            "job_id": "job-7",
            "command": ["melix"],
            "cwd": "",
            "log_path": "/tmp/job.log",
            "session_id": "session-7",
            "status": "pending",
            "followup_status": "not_started",
        },
        {
            "schema_version": RECORD_SCHEMA_VERSION,
            "job_id": "job-7",
            "command": ["melix"],
            "cwd": "/workspace",
            "log_path": "/tmp/job.log",
            "session_id": "session-7",
            "status": "done",
            "followup_status": "not_started",
        },
        {
            "schema_version": RECORD_SCHEMA_VERSION,
            "job_id": "job-7",
            "command": ["melix"],
            "cwd": "/workspace",
            "log_path": "/tmp/job.log",
            "session_id": "session-7",
            "status": "pending",
            "followup_status": "later",
        },
        {
            "schema_version": RECORD_SCHEMA_VERSION,
            "job_id": "job-7",
            "command": ["melix"],
            "cwd": "/workspace",
            "log_path": "/tmp/job.log",
            "session_id": "session-7",
            "status": "pending",
            "followup_status": "not_started",
            "revision": -1,
        },
        {
            "schema_version": RECORD_SCHEMA_VERSION,
            "job_id": "job-7",
            "command": ["melix"],
            "cwd": "/workspace",
            "log_path": "/tmp/job.log",
            "session_id": "session-7",
            "status": "pending",
            "followup_status": "not_started",
            "timeout_seconds": -1,
        },
        {
            "schema_version": RECORD_SCHEMA_VERSION,
            "job_id": "job-7",
            "command": ["melix"],
            "cwd": "/workspace",
            "log_path": "/tmp/job.log",
            "session_id": "session-7",
            "status": "pending",
            "followup_status": "not_started",
            "exit_status": True,
        },
        {
            "schema_version": RECORD_SCHEMA_VERSION,
            "job_id": "job-7",
            "command": ["melix"],
            "cwd": "/workspace",
            "log_path": "/tmp/job.log",
            "session_id": "session-7",
            "status": "pending",
            "followup_status": "not_started",
            "revision": True,
        },
        {
            "schema_version": RECORD_SCHEMA_VERSION,
            "job_id": "job-7",
            "command": ["melix"],
            "cwd": "/workspace",
            "log_path": "/tmp/job.log",
            "session_id": "session-7",
            "status": "pending",
            "followup_status": "not_started",
            "followup_session_id": 7,
        },
        {
            "schema_version": RECORD_SCHEMA_VERSION,
            "job_id": "job-7",
            "command": ["melix"],
            "cwd": "/workspace",
            "log_path": "/tmp/job.log",
            "session_id": "session-7",
            "status": "pending",
            "followup_status": "not_started",
            "artifact_paths": "/tmp/artifact.json",
        },
        {
            "schema_version": RECORD_SCHEMA_VERSION,
            "job_id": "job-7",
            "command": ["melix"],
            "cwd": "/workspace",
            "log_path": "/tmp/job.log",
            "session_id": "session-7",
            "status": "pending",
            "followup_status": "not_started",
            "artifact_paths": [7],
        },
        {
            "schema_version": RECORD_SCHEMA_VERSION,
            "job_id": "",
            "command": ["melix"],
            "cwd": "/workspace",
            "log_path": "/tmp/job.log",
            "session_id": "session-7",
            "status": "pending",
            "followup_status": "not_started",
        },
    ),
)
def test_record_from_dict_rejects_malformed_persisted_state(payload: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        LocalJobContinuationRecord.from_dict(payload)


def test_record_validation_rejects_malformed_dataclass_fields() -> None:
    with pytest.raises(ValueError):
        _record(command=("",)).to_dict()
    with pytest.raises(ValueError):
        _record(exit_status=True).to_dict()
    with pytest.raises(ValueError):
        _record(timeout_seconds=True).to_dict()
    with pytest.raises(ValueError):
        _record(followup_session_id=7).to_dict()
    with pytest.raises(ValueError):
        _record(artifact_paths=(7,)).to_dict()
