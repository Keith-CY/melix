from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, replace
from errno import EPERM
from pathlib import Path
from typing import Any, Iterator, Sequence
from uuid import uuid4

from worker.runtime.background_continuation import (
    BackgroundContinuationAdmissionError,
    admit_background_continuation,
)
from worker.runtime.prompt_context import PromptContextAdmission
from worker.runtime.untrusted_context import UNTRUSTED_CONTEXT_RECEIPT_SCHEMA_VERSION


RECORD_SCHEMA_VERSION = "melix.local_job_continuation_record.v1"
RECEIPT_SCHEMA_VERSION = "melix.local_job_continuation_receipt.v1"

JOB_STATUSES = frozenset({"pending", "running", "completed", "failed", "timeout", "blocked"})
FOLLOWUP_STATUSES = frozenset({"not_started", "pending", "in_progress", "completed", "blocked"})
JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


class LocalJobContinuationStoreError(RuntimeError):
    def __init__(self, message: str, *, receipt: dict[str, Any]) -> None:
        super().__init__(message)
        self.receipt = receipt


class LocalJobContinuationAdmissionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        reconciliation: LocalJobContinuationReconciliation | None,
        refusal_receipts: list[dict[str, Any]],
    ) -> None:
        super().__init__(message)
        self.reconciliation = reconciliation
        self.refusal_receipts = refusal_receipts


@dataclass(frozen=True, slots=True)
class LocalJobContinuationRecord:
    job_id: str
    command: tuple[str, ...]
    cwd: str
    log_path: str
    session_id: str
    status: str = "pending"
    exit_status: int | None = None
    timeout_seconds: int | None = None
    followup_status: str = "not_started"
    followup_session_id: str = ""
    followed_up_at: str = ""
    success_marker_path: str = ""
    artifact_paths: tuple[str, ...] = ()
    revision: int = 0

    def to_dict(self) -> dict[str, Any]:
        _validate_record(self)
        return {
            "schema_version": RECORD_SCHEMA_VERSION,
            "job_id": self.job_id,
            "command": list(self.command),
            "cwd": self.cwd,
            "log_path": self.log_path,
            "session_id": self.session_id,
            "status": self.status,
            "exit_status": self.exit_status,
            "timeout_seconds": self.timeout_seconds,
            "followup_status": self.followup_status,
            "followup_session_id": self.followup_session_id,
            "followed_up_at": self.followed_up_at,
            "success_marker_path": self.success_marker_path,
            "artifact_paths": list(self.artifact_paths),
            "revision": self.revision,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> LocalJobContinuationRecord:
        if payload.get("schema_version") != RECORD_SCHEMA_VERSION:
            raise ValueError("unsupported local job continuation record schema")
        record = cls(
            job_id=_required_text(payload, "job_id"),
            command=tuple(_required_text_list(payload, "command")),
            cwd=_required_text(payload, "cwd"),
            log_path=_required_text(payload, "log_path"),
            session_id=_required_text(payload, "session_id"),
            status=_required_text(payload, "status"),
            exit_status=_optional_int(payload.get("exit_status"), "exit_status"),
            timeout_seconds=_optional_int(payload.get("timeout_seconds"), "timeout_seconds"),
            followup_status=_required_text(payload, "followup_status"),
            followup_session_id=_optional_text(payload, "followup_session_id"),
            followed_up_at=_optional_text(payload, "followed_up_at"),
            success_marker_path=_optional_text(payload, "success_marker_path"),
            artifact_paths=tuple(_optional_text_list(payload, "artifact_paths")),
            revision=_optional_int(payload.get("revision", 0), "revision") or 0,
        )
        _validate_record(record)
        return record

    def with_revision(self, revision: int) -> LocalJobContinuationRecord:
        parsed_revision = _optional_int(revision, "revision")
        if parsed_revision is None:
            raise ValueError("revision must be an integer")
        if parsed_revision < 0:
            raise ValueError("local job continuation revision must be non-negative")
        return replace(self, revision=parsed_revision)


@dataclass(frozen=True, slots=True)
class LocalJobLiveEvidence:
    session_id: str
    active: bool
    progress_excerpt: str = ""
    exit_status: int | None = None
    success_marker_path: str = ""
    artifact_paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LocalJobContinuationReconciliation:
    record: LocalJobContinuationRecord
    receipt: dict[str, Any]


@dataclass(frozen=True, slots=True)
class LocalJobContinuationFollowupClaim:
    reconciliation: LocalJobContinuationReconciliation
    prompt_context: PromptContextAdmission


@dataclass(frozen=True, slots=True)
class LocalJobContinuationFollowupClaimBatch:
    claims: tuple[LocalJobContinuationFollowupClaim, ...]
    receipts: tuple[dict[str, Any], ...]
    refusal_receipts: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class LocalJobContinuationFollowupCandidate:
    record: LocalJobContinuationRecord
    receipt: dict[str, Any]


@dataclass(frozen=True, slots=True)
class LocalJobContinuationFollowupScan:
    candidates: tuple[LocalJobContinuationFollowupCandidate, ...]
    receipts: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class LocalJobSessionFollowupProjection:
    claim: LocalJobContinuationFollowupClaim
    claim_receipt: dict[str, Any]
    prompt_user_payload: dict[str, Any]
    untrusted_context_receipts: list[dict[str, object]]
    followup_message: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class LocalJobSessionFollowupProjectionBatch:
    claim_batch: LocalJobContinuationFollowupClaimBatch
    projections: tuple[LocalJobSessionFollowupProjection, ...]
    followup_messages: tuple[dict[str, Any], ...]
    receipts: tuple[dict[str, Any], ...]
    refusal_receipts: tuple[dict[str, Any], ...]


class LocalJobContinuationStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def load_record(self, job_id: str) -> LocalJobContinuationRecord | None:
        path = self._record_path(job_id)
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        return LocalJobContinuationRecord.from_dict(json.loads(content))

    def save_record(
        self,
        record: LocalJobContinuationRecord,
        *,
        expected_revision: int | None = None,
    ) -> LocalJobContinuationRecord:
        _validate_record(record)
        path = self._record_path(record.job_id)
        self.root.mkdir(parents=True, exist_ok=True)
        with self._record_write_lock(path):
            current = self.load_record(record.job_id)
            current_revision = current.revision if current is not None else None
            if expected_revision is not None and current_revision != expected_revision:
                raise LocalJobContinuationStoreError(
                    "local job continuation record revision changed",
                    receipt=_receipt(
                        job_id=record.job_id,
                        status="blocked",
                        reason="record_revision_mismatch",
                        session_id=record.session_id,
                        exit_status=record.exit_status,
                        followup_status=record.followup_status,
                        duplicate_launch_refused=False,
                        completion_evidence_available=_has_completion_evidence(record),
                        corrective_action=(
                            "Reload the local job continuation record before writing a new update."
                        ),
                    ),
                )
            next_revision = 0 if current_revision is None else current_revision + 1
            next_record = record.with_revision(next_revision)
            tmp_path = path.with_suffix(path.suffix + ".tmp")
            tmp_path.write_text(
                json.dumps(next_record.to_dict(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            tmp_path.replace(path)
            return next_record

    def reconcile_record(
        self,
        job_id: str,
        *,
        live_evidence: LocalJobLiveEvidence | None = None,
    ) -> LocalJobContinuationReconciliation | None:
        record = self.load_record(job_id)
        if record is None:
            return None

        result = reconcile_local_job_continuation(record, live_evidence=live_evidence)
        if result.record == record:
            return result

        saved = self.save_record(result.record, expected_revision=record.revision)
        return LocalJobContinuationReconciliation(record=saved, receipt=result.receipt)

    def claim_followup(
        self,
        job_id: str,
        *,
        followup_session_id: str,
        live_evidence: LocalJobLiveEvidence | None = None,
    ) -> LocalJobContinuationReconciliation | None:
        record = self.load_record(job_id)
        if record is None:
            return None

        result = claim_local_job_followup(
            record,
            followup_session_id=followup_session_id,
            live_evidence=live_evidence,
        )
        if result.record == record:
            return result

        saved = self.save_record(result.record, expected_revision=record.revision)
        return LocalJobContinuationReconciliation(record=saved, receipt=result.receipt)

    def claim_followup_prompt_context(
        self,
        job_id: str,
        *,
        followup_session_id: str,
        completion_summary: dict[str, Any],
        owner_scope_checked: bool,
        live_evidence: LocalJobLiveEvidence | None = None,
    ) -> LocalJobContinuationFollowupClaim | None:
        record = self.load_record(job_id)
        if record is None:
            return None

        result = claim_local_job_followup(
            record,
            followup_session_id=followup_session_id,
            live_evidence=live_evidence,
        )
        if result.record == record:
            return LocalJobContinuationFollowupClaim(
                reconciliation=result,
                prompt_context=PromptContextAdmission(
                    user_payload={},
                    untrusted_context_receipts=[],
                ),
            )
        if result.receipt.get("reason") != "followup_claimed":
            saved = self.save_record(result.record, expected_revision=record.revision)
            return LocalJobContinuationFollowupClaim(
                reconciliation=replace(result, record=saved),
                prompt_context=PromptContextAdmission(
                    user_payload={},
                    untrusted_context_receipts=[],
                ),
            )

        try:
            prompt_context = admit_background_continuation(
                job_id=result.record.job_id,
                job_summary=completion_summary,
                owner_scope_checked=owner_scope_checked,
                segment_id=f"{result.record.job_id}:local-job-followup",
                source_field="local_job_completion_summary",
                reason="local job completion summary is prompt data, not instructions",
                corrective_action=(
                    "Keep local job completion summaries in user-role data context and do not "
                    "project them into system or developer instructions."
                ),
            )
        except BackgroundContinuationAdmissionError as exc:
            raise LocalJobContinuationAdmissionError(
                "Invalid local job follow-up prompt context.",
                reconciliation=LocalJobContinuationReconciliation(
                    record=record,
                    receipt=_receipt(
                        job_id=record.job_id,
                        status=record.status,
                        reason="followup_prompt_context_refused",
                        session_id=record.session_id,
                        exit_status=record.exit_status,
                        followup_status=record.followup_status,
                        duplicate_launch_refused=False,
                        completion_evidence_available=_has_completion_evidence(
                            record,
                            live_evidence,
                        ),
                        corrective_action=(
                            "Fix the local job follow-up prompt context before claiming "
                            "the follow-up."
                        ),
                        followup_session_id=record.followup_session_id,
                    ),
                ),
                refusal_receipts=exc.refusal_receipts,
            ) from exc

        saved = self.save_record(result.record, expected_revision=record.revision)
        return LocalJobContinuationFollowupClaim(
            reconciliation=replace(result, record=saved),
            prompt_context=prompt_context,
        )

    def scan_followup_candidates(
        self,
        *,
        live_evidence_by_job_id: dict[str, LocalJobLiveEvidence] | None = None,
    ) -> LocalJobContinuationFollowupScan:
        candidates: list[LocalJobContinuationFollowupCandidate] = []
        receipts: list[dict[str, Any]] = []
        live_evidence_by_job_id = live_evidence_by_job_id or {}
        root = self.root
        try:
            record_names = sorted(
                entry.name
                for entry in os.scandir(os.fspath(root))
                if entry.name.endswith(".json") and entry.is_file()
            )
        except FileNotFoundError:
            return LocalJobContinuationFollowupScan(candidates=(), receipts=())
        for record_name in record_names:
            path = root / record_name
            job_id = path.stem
            try:
                reconciliation = self.reconcile_record(
                    job_id,
                    live_evidence=live_evidence_by_job_id.get(job_id),
                )
            except LocalJobContinuationStoreError as exc:
                receipts.append(exc.receipt)
                continue
            except (json.JSONDecodeError, OSError, ValueError):
                receipts.append(_unreadable_record_scan_receipt(job_id=job_id))
                continue
            if reconciliation is None:
                continue
            receipt = _followup_candidate_scan_receipt(reconciliation.record)
            # Scan-level follow-up state wins for ready or already-claimed records.
            # Otherwise surface reconciliation changes before the generic scan result.
            if receipt["reason"] == "followup_candidate_ready":
                receipts.append(receipt)
                candidates.append(
                    LocalJobContinuationFollowupCandidate(
                        record=reconciliation.record,
                        receipt=receipt,
                    )
                )
            elif receipt["reason"] == "followup_already_claimed":
                receipts.append(receipt)
            elif reconciliation.receipt.get("reason") != "record_state_preserved":
                receipts.append(reconciliation.receipt)
            else:
                receipts.append(receipt)

        return LocalJobContinuationFollowupScan(
            candidates=tuple(candidates),
            receipts=tuple(receipts),
        )

    def claim_scanned_followup_prompt_contexts(
        self,
        *,
        followup_session_ids_by_job_id: dict[str, str] | None,
        completion_summaries_by_job_id: dict[str, dict[str, Any]] | None,
        owner_scope_checked_by_job_id: dict[str, bool] | None,
        live_evidence_by_job_id: dict[str, LocalJobLiveEvidence] | None = None,
    ) -> LocalJobContinuationFollowupClaimBatch:
        live_evidence_by_job_id = live_evidence_by_job_id or {}
        (
            followup_session_ids_by_job_id,
            followup_session_ids_input_error,
        ) = _claim_input_mapping_or_error(
            followup_session_ids_by_job_id,
            "followup_session_ids_by_job_id",
        )
        (
            completion_summaries_by_job_id,
            completion_summaries_input_error,
        ) = _claim_input_mapping_or_error(
            completion_summaries_by_job_id,
            "completion_summaries_by_job_id",
        )
        (
            owner_scope_checked_by_job_id,
            owner_scope_checked_input_error,
        ) = _claim_input_mapping_or_error(
            owner_scope_checked_by_job_id,
            "owner_scope_checked_by_job_id",
        )
        wrapper_input_error = (
            followup_session_ids_input_error
            or completion_summaries_input_error
            or owner_scope_checked_input_error
        )
        scan = self.scan_followup_candidates(
            live_evidence_by_job_id=live_evidence_by_job_id,
        )
        claims: list[LocalJobContinuationFollowupClaim] = []
        receipts = list(scan.receipts)
        refusal_receipts: list[dict[str, Any]] = []

        for candidate in scan.candidates:
            job_id = candidate.record.job_id
            if wrapper_input_error is not None:
                receipts.append(
                    _followup_claim_input_invalid_receipt(
                        candidate.record,
                        error=wrapper_input_error,
                    )
                )
                continue
            try:
                missing_fields = [
                    field_name
                    for field_name, values in (
                        ("followup_session_id", followup_session_ids_by_job_id),
                        ("completion_summary", completion_summaries_by_job_id),
                        ("owner_scope_checked", owner_scope_checked_by_job_id),
                    )
                    if job_id not in values
                ]
            except (LookupError, TypeError, ValueError) as exc:
                receipts.append(
                    _followup_claim_input_invalid_receipt(
                        candidate.record,
                        error=str(exc),
                    )
                )
                continue
            if missing_fields:
                receipts.append(
                    _followup_claim_input_missing_receipt(
                        candidate.record,
                        missing_fields=missing_fields,
                    )
                )
                continue

            try:
                # Keep this try block scoped to the claim call so ValueError maps only claim-input validation.
                claim = self.claim_followup_prompt_context(
                    job_id,
                    followup_session_id=_claim_input_value(
                        followup_session_ids_by_job_id,
                        job_id,
                    ),
                    completion_summary=_claim_input_value(
                        completion_summaries_by_job_id,
                        job_id,
                    ),
                    owner_scope_checked=_claim_input_value(
                        owner_scope_checked_by_job_id,
                        job_id,
                    ),
                    live_evidence=live_evidence_by_job_id.get(job_id),
                )
            except LocalJobContinuationAdmissionError as exc:
                if exc.reconciliation is not None:
                    receipts.append(exc.reconciliation.receipt)
                else:
                    receipts.append(_followup_prompt_context_refused_receipt(candidate.record))
                refusal_receipts.extend(exc.refusal_receipts)
                continue
            except LocalJobContinuationStoreError as exc:
                receipts.append(exc.receipt)
                continue
            except ValueError as exc:
                receipts.append(
                    _followup_claim_input_invalid_receipt(
                        candidate.record,
                        error=str(exc),
                    )
                )
                continue

            if claim is None:
                receipts.append(_followup_record_missing_receipt(candidate.record))
                continue
            receipts.append(claim.reconciliation.receipt)
            if claim.reconciliation.receipt.get("reason") == "followup_claimed":
                claims.append(claim)

        return LocalJobContinuationFollowupClaimBatch(
            claims=tuple(claims),
            receipts=tuple(receipts),
            refusal_receipts=tuple(refusal_receipts),
        )

    def _record_path(self, job_id: str) -> Path:
        safe_job_id = _safe_job_id(job_id)
        return self.root / f"{safe_job_id}.json"

    @contextmanager
    def _record_write_lock(self, path: Path) -> Iterator[None]:
        lock_path = path.with_suffix(path.suffix + ".lock")
        fd: int | None = None
        try:
            fd = self._open_record_lock(lock_path)
            os.write(fd, f"{os.getpid()}\n".encode("utf-8"))
            yield
        except FileExistsError as exc:
            raise LocalJobContinuationStoreError(
                "local job continuation record is locked by another writer",
                receipt=_receipt(
                    job_id=path.stem,
                    status="blocked",
                    reason="record_write_locked",
                    session_id="",
                    exit_status=None,
                    followup_status="blocked",
                    duplicate_launch_refused=False,
                    completion_evidence_available=False,
                    corrective_action="Retry after the active local job record writer finishes.",
                ),
            ) from exc
        finally:
            if fd is not None:
                os.close(fd)
                try:
                    lock_path.unlink()
                except OSError:
                    pass

    def _open_record_lock(self, lock_path: Path) -> int:
        try:
            return os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if self._remove_stale_record_lock(lock_path):
                try:
                    return os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                except FileExistsError:
                    pass
            raise

    def _remove_stale_record_lock(self, lock_path: Path) -> bool:
        guard_path = lock_path.with_name(f"{lock_path.name}.recovery")
        guard_fd = self._open_record_lock_recovery_guard(guard_path)
        if guard_fd is None:
            return False
        try:
            try:
                raw_pid = lock_path.read_text(encoding="utf-8").strip()
                pid = int(raw_pid)
            except FileNotFoundError:
                return True
            except (OSError, ValueError):
                return False
            if pid <= 0 or _process_is_active(pid):
                return False

            temp_path = lock_path.with_name(f"{lock_path.name}.stale.{os.getpid()}.{uuid4().hex}")
            try:
                os.rename(lock_path, temp_path)
            except FileNotFoundError:
                return True
            except OSError:
                return False

            try:
                current_pid = int(temp_path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                self._restore_renamed_record_lock(temp_path, lock_path)
                return False
            if current_pid != pid or _process_is_active(current_pid):
                self._restore_renamed_record_lock(temp_path, lock_path)
                return False
            try:
                temp_path.unlink()
            except FileNotFoundError:
                return True
            except OSError:
                self._restore_renamed_record_lock(temp_path, lock_path)
                return False
            return True
        finally:
            os.close(guard_fd)
            try:
                guard_path.unlink()
            except OSError:
                pass

    def _open_record_lock_recovery_guard(self, guard_path: Path) -> int | None:
        try:
            fd = os.open(guard_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if not self._remove_stale_record_lock_recovery_guard(guard_path):
                return None
            try:
                fd = os.open(guard_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                return None
        os.write(fd, f"{os.getpid()}\n".encode("utf-8"))
        return fd

    def _remove_stale_record_lock_recovery_guard(self, guard_path: Path) -> bool:
        try:
            raw_pid = guard_path.read_text(encoding="utf-8").strip()
            pid = int(raw_pid)
        except (OSError, ValueError):
            return False
        if pid <= 0 or _process_is_active(pid):
            return False
        try:
            guard_path.unlink()
        except FileNotFoundError:
            return True
        except OSError:
            return False
        return True

    def _restore_renamed_record_lock(self, temp_path: Path, lock_path: Path) -> None:
        try:
            os.link(temp_path, lock_path)
        except FileExistsError:
            pass
        except OSError:
            return
        try:
            temp_path.unlink()
        except OSError:
            pass


def reconcile_local_job_continuation(
    record: LocalJobContinuationRecord,
    *,
    live_evidence: LocalJobLiveEvidence | None = None,
) -> LocalJobContinuationReconciliation:
    _validate_record(record)
    evidence_available = _has_completion_evidence(record, live_evidence)
    live_matches = _live_session_matches(record, live_evidence)

    if live_matches and live_evidence is not None and live_evidence.active:
        if record.status == "completed" and not evidence_available:
            revived = replace(record, status="running", exit_status=None)
            return LocalJobContinuationReconciliation(
                record=revived,
                receipt=_receipt(
                    job_id=record.job_id,
                    status="running",
                    reason="stale_done_revived",
                    session_id=record.session_id,
                    exit_status=None,
                    followup_status=record.followup_status,
                    duplicate_launch_refused=True,
                    completion_evidence_available=False,
                    corrective_action=(
                        "Reattach to the live local job session and wait for explicit "
                        "success marker or artifact evidence before completing."
                    ),
                ),
            )
        if record.status in {"pending", "running"}:
            running = replace(record, status="running", exit_status=live_evidence.exit_status)
            return LocalJobContinuationReconciliation(
                record=running,
                receipt=_receipt(
                    job_id=record.job_id,
                    status="running",
                    reason="live_session_reused",
                    session_id=record.session_id,
                    exit_status=live_evidence.exit_status,
                    followup_status=record.followup_status,
                    duplicate_launch_refused=True,
                    completion_evidence_available=evidence_available,
                    corrective_action=(
                        "Reuse the active local job session instead of launching duplicate work."
                    ),
                ),
            )

    if record.status == "completed":
        if evidence_available:
            completed = _record_with_live_completion_evidence(record, live_evidence)
            return LocalJobContinuationReconciliation(
                record=completed,
                receipt=_receipt(
                    job_id=record.job_id,
                    status="completed",
                    reason="completion_evidence_accepted",
                    session_id=record.session_id,
                    exit_status=record.exit_status,
                    followup_status=record.followup_status,
                    duplicate_launch_refused=False,
                    completion_evidence_available=True,
                    corrective_action="The monitor may enqueue exactly one follow-up for this job.",
                ),
            )
        blocked = replace(record, status="blocked")
        return LocalJobContinuationReconciliation(
            record=blocked,
            receipt=_receipt(
                job_id=record.job_id,
                status="blocked",
                reason="missing_completion_evidence",
                session_id=record.session_id,
                exit_status=record.exit_status,
                followup_status=record.followup_status,
                duplicate_launch_refused=False,
                completion_evidence_available=False,
                corrective_action=(
                    "Require a success marker or artifact path before treating the local job as complete."
                ),
            ),
        )

    return LocalJobContinuationReconciliation(
        record=record,
        receipt=_receipt(
            job_id=record.job_id,
            status=record.status,
            reason="record_state_preserved",
            session_id=record.session_id,
            exit_status=record.exit_status,
            followup_status=record.followup_status,
            duplicate_launch_refused=False,
            completion_evidence_available=evidence_available,
            corrective_action="No reconciliation change was required for this local job record.",
        ),
    )


def claim_local_job_followup(
    record: LocalJobContinuationRecord,
    *,
    followup_session_id: str,
    live_evidence: LocalJobLiveEvidence | None = None,
) -> LocalJobContinuationReconciliation:
    _validate_record(record)
    normalized_followup_session_id = _required_runtime_text(
        followup_session_id,
        "followup_session_id",
    )
    reconciled = reconcile_local_job_continuation(record, live_evidence=live_evidence)
    record = reconciled.record
    evidence_available = _has_completion_evidence(record, live_evidence)

    if reconciled.receipt.get("reason") == "missing_completion_evidence":
        return reconciled

    if record.followup_status in {"pending", "in_progress", "completed"}:
        return LocalJobContinuationReconciliation(
            record=record,
            receipt=_receipt(
                job_id=record.job_id,
                status=record.status,
                reason="followup_already_claimed",
                session_id=record.session_id,
                exit_status=record.exit_status,
                followup_status=record.followup_status,
                duplicate_launch_refused=False,
                completion_evidence_available=evidence_available,
                corrective_action=(
                    "Do not enqueue another local job follow-up for this record."
                ),
                followup_session_id=record.followup_session_id,
            ),
        )

    if record.status != "completed":
        return LocalJobContinuationReconciliation(
            record=record,
            receipt=_receipt(
                job_id=record.job_id,
                status=record.status,
                reason="followup_not_ready",
                session_id=record.session_id,
                exit_status=record.exit_status,
                followup_status=record.followup_status,
                duplicate_launch_refused=False,
                completion_evidence_available=evidence_available,
                corrective_action=(
                    "Wait until the local job is completed with explicit evidence before follow-up."
                ),
                followup_session_id=record.followup_session_id,
            ),
        )

    claimed = replace(
        record,
        followup_status="in_progress",
        followup_session_id=normalized_followup_session_id,
    )
    return LocalJobContinuationReconciliation(
        record=claimed,
        receipt=_receipt(
            job_id=record.job_id,
            status=claimed.status,
            reason="followup_claimed",
            session_id=claimed.session_id,
            exit_status=claimed.exit_status,
            followup_status=claimed.followup_status,
            duplicate_launch_refused=False,
            completion_evidence_available=True,
            corrective_action=(
                "The monitor may project exactly one admitted background continuation."
            ),
            followup_session_id=claimed.followup_session_id,
            prompt_context_receipts=_local_job_followup_prompt_context_receipts(claimed),
        ),
    )


def project_local_job_session_followup(
    store: LocalJobContinuationStore,
    *,
    job_id: str,
    followup_session_id: str,
    completion_summary: dict[str, Any],
    owner_scope_checked: bool,
    live_evidence: LocalJobLiveEvidence | None = None,
) -> LocalJobSessionFollowupProjection | None:
    claim = store.claim_followup_prompt_context(
        job_id,
        followup_session_id=followup_session_id,
        completion_summary=completion_summary,
        owner_scope_checked=owner_scope_checked,
        live_evidence=live_evidence,
    )
    if claim is None:
        return None

    return _project_local_job_session_followup_claim(claim)


def project_local_job_session_followups(
    store: LocalJobContinuationStore,
    *,
    followup_session_ids_by_job_id: dict[str, str] | None,
    completion_summaries_by_job_id: dict[str, dict[str, Any]] | None,
    owner_scope_checked_by_job_id: dict[str, bool] | None,
    live_evidence_by_job_id: dict[str, LocalJobLiveEvidence] | None = None,
) -> LocalJobSessionFollowupProjectionBatch:
    claim_batch = store.claim_scanned_followup_prompt_contexts(
        followup_session_ids_by_job_id=followup_session_ids_by_job_id,
        completion_summaries_by_job_id=completion_summaries_by_job_id,
        owner_scope_checked_by_job_id=owner_scope_checked_by_job_id,
        live_evidence_by_job_id=live_evidence_by_job_id,
    )
    projections: list[LocalJobSessionFollowupProjection] = []
    followup_messages: list[dict[str, Any]] = []

    for claim in claim_batch.claims:
        projection = _project_local_job_session_followup_claim(claim)
        projections.append(projection)
        if projection.followup_message is not None:
            followup_messages.append(deepcopy(projection.followup_message))

    return LocalJobSessionFollowupProjectionBatch(
        claim_batch=claim_batch,
        projections=tuple(projections),
        followup_messages=tuple(followup_messages),
        receipts=deepcopy(claim_batch.receipts),
        refusal_receipts=deepcopy(claim_batch.refusal_receipts),
    )


def _project_local_job_session_followup_claim(
    claim: LocalJobContinuationFollowupClaim,
) -> LocalJobSessionFollowupProjection:
    prompt_user_payload = deepcopy(claim.prompt_context.user_payload)
    receipts = deepcopy(claim.prompt_context.untrusted_context_receipts)
    followup_message: dict[str, Any] | None = None
    if prompt_user_payload:
        followup_message = {
            "role": "user",
            "content": prompt_user_payload,
            "untrusted_context_receipts": receipts,
        }
    return LocalJobSessionFollowupProjection(
        claim=claim,
        claim_receipt=deepcopy(claim.reconciliation.receipt),
        prompt_user_payload=prompt_user_payload,
        untrusted_context_receipts=receipts,
        followup_message=followup_message,
    )


def _claim_input_mapping_or_error(
    value: Any,
    field_name: str,
) -> tuple[Mapping[str, Any], str | None]:
    if value is None:
        return {}, None
    if isinstance(value, Mapping):
        return value, None
    return {}, f"{field_name} must be a mapping when provided"


def _claim_input_value(values: Mapping[str, Any], job_id: str) -> Any:
    try:
        return values[job_id]
    except (LookupError, TypeError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


def _receipt(
    *,
    job_id: str,
    status: str,
    reason: str,
    session_id: str,
    exit_status: int | None,
    followup_status: str,
    duplicate_launch_refused: bool,
    completion_evidence_available: bool,
    corrective_action: str,
    followup_session_id: str = "",
    prompt_context_receipts: Sequence[dict[str, object]] = (),
) -> dict[str, Any]:
    receipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "job_id": job_id,
        "status": status,
        "reason": reason,
        "session_id": session_id,
        "exit_status": exit_status,
        "followup_status": followup_status,
        "followup_session_id": followup_session_id,
        "duplicate_launch_refused": duplicate_launch_refused,
        "completion_evidence_available": completion_evidence_available,
        "corrective_action": corrective_action,
    }
    if prompt_context_receipts:
        receipt["prompt_context_receipt_schema"] = UNTRUSTED_CONTEXT_RECEIPT_SCHEMA_VERSION
        receipt["prompt_context_receipt_count"] = len(prompt_context_receipts)
        receipt["prompt_context_receipts"] = [dict(item) for item in prompt_context_receipts]
    return receipt


def _followup_candidate_scan_receipt(
    record: LocalJobContinuationRecord,
) -> dict[str, Any]:
    evidence_available = _has_completion_evidence(record)
    if record.followup_status in {"pending", "in_progress", "completed"}:
        return _receipt(
            job_id=record.job_id,
            status=record.status,
            reason="followup_already_claimed",
            session_id=record.session_id,
            exit_status=record.exit_status,
            followup_status=record.followup_status,
            duplicate_launch_refused=False,
            completion_evidence_available=evidence_available,
            corrective_action="Do not enqueue another local job follow-up for this record.",
            followup_session_id=record.followup_session_id,
        )
    if record.status == "completed" and evidence_available:
        return _receipt(
            job_id=record.job_id,
            status=record.status,
            reason="followup_candidate_ready",
            session_id=record.session_id,
            exit_status=record.exit_status,
            followup_status=record.followup_status,
            duplicate_launch_refused=False,
            completion_evidence_available=True,
            corrective_action=(
                "A monitor may claim this local job follow-up after prompt-context admission."
            ),
        )
    # A non-ready record only means the monitor may not claim it yet; callers
    # that need running-vs-blocked detail should inspect the status field.
    return _receipt(
        job_id=record.job_id,
        status=record.status,
        reason="followup_not_ready",
        session_id=record.session_id,
        exit_status=record.exit_status,
        followup_status=record.followup_status,
        duplicate_launch_refused=False,
        completion_evidence_available=evidence_available,
        corrective_action=(
            "Wait until the local job is completed with explicit evidence before follow-up."
        ),
        followup_session_id=record.followup_session_id,
    )


def _unreadable_record_scan_receipt(*, job_id: str) -> dict[str, Any]:
    return _receipt(
        job_id=job_id,
        status="blocked",
        reason="record_unreadable",
        session_id="",
        exit_status=None,
        followup_status="blocked",
        duplicate_launch_refused=False,
        completion_evidence_available=False,
        corrective_action=(
            "Repair or remove the unreadable local job continuation record before "
            "it can be considered for follow-up."
        ),
    )


def _followup_claim_input_missing_receipt(
    record: LocalJobContinuationRecord,
    *,
    missing_fields: Sequence[str],
) -> dict[str, Any]:
    receipt = _receipt(
        job_id=record.job_id,
        status=record.status,
        reason="followup_claim_input_missing",
        session_id=record.session_id,
        exit_status=record.exit_status,
        followup_status=record.followup_status,
        duplicate_launch_refused=False,
        completion_evidence_available=_has_completion_evidence(record),
        corrective_action=(
            "Provide a follow-up session ID, redacted completion summary, and "
            "owner-scope decision before claiming this local job follow-up."
        ),
        followup_session_id=record.followup_session_id,
    )
    receipt["missing_fields"] = list(missing_fields)
    return receipt


def _followup_claim_input_invalid_receipt(
    record: LocalJobContinuationRecord,
    *,
    error: str,
) -> dict[str, Any]:
    receipt = _receipt(
        job_id=record.job_id,
        status=record.status,
        reason="followup_claim_input_invalid",
        session_id=record.session_id,
        exit_status=record.exit_status,
        followup_status=record.followup_status,
        duplicate_launch_refused=False,
        completion_evidence_available=_has_completion_evidence(record),
        corrective_action=(
            "Fix the local job follow-up claim inputs before claiming this record."
        ),
        followup_session_id=record.followup_session_id,
    )
    receipt["input_error"] = error
    return receipt


def _followup_prompt_context_refused_receipt(
    record: LocalJobContinuationRecord,
) -> dict[str, Any]:
    return _receipt(
        job_id=record.job_id,
        status=record.status,
        reason="followup_prompt_context_refused",
        session_id=record.session_id,
        exit_status=record.exit_status,
        followup_status=record.followup_status,
        duplicate_launch_refused=False,
        completion_evidence_available=_has_completion_evidence(record),
        corrective_action=(
            "Keep this local job follow-up unclaimed until prompt-context admission succeeds."
        ),
        followup_session_id=record.followup_session_id,
    )


def _followup_record_missing_receipt(
    record: LocalJobContinuationRecord,
) -> dict[str, Any]:
    return _receipt(
        job_id=record.job_id,
        # The record disappeared before claim, so the scan snapshot is no longer actionable.
        status="blocked",
        reason="followup_record_missing",
        session_id=record.session_id,
        exit_status=record.exit_status,
        followup_status=record.followup_status,
        duplicate_launch_refused=False,
        completion_evidence_available=_has_completion_evidence(record),
        corrective_action=(
            "Rescan local job continuation records before attempting another follow-up claim."
        ),
        followup_session_id=record.followup_session_id,
    )


def _local_job_followup_prompt_context_receipts(
    record: LocalJobContinuationRecord,
) -> list[dict[str, object]]:
    admission = admit_background_continuation(
        job_id=record.job_id,
        job_summary={
            "job_id": record.job_id,
            "status": record.status,
            "exit_status": record.exit_status,
            "followup_status": record.followup_status,
        },
        owner_scope_checked=False,
        segment_id=f"{record.job_id}:local-job-followup",
        source_field="local_job_followup",
        reason="local job follow-up is prompt data, not instructions",
        corrective_action="Keep local job follow-up evidence in user-role prompt context.",
    )
    return admission.untrusted_context_receipts


def _has_completion_evidence(
    record: LocalJobContinuationRecord,
    live_evidence: LocalJobLiveEvidence | None = None,
) -> bool:
    if record.success_marker_path.strip() or any(path.strip() for path in record.artifact_paths):
        return True
    if live_evidence is None:
        return False
    return bool(
        live_evidence.success_marker_path.strip()
        or any(path.strip() for path in live_evidence.artifact_paths)
    )


def _record_with_live_completion_evidence(
    record: LocalJobContinuationRecord,
    live_evidence: LocalJobLiveEvidence | None,
) -> LocalJobContinuationRecord:
    if live_evidence is None:
        return record
    success_marker_path = (
        record.success_marker_path.strip() or live_evidence.success_marker_path.strip()
    )
    artifact_paths = tuple(
        dict.fromkeys(
            stripped_path
            for path in (*record.artifact_paths, *live_evidence.artifact_paths)
            if (stripped_path := path.strip())
        )
    )
    if (
        success_marker_path == record.success_marker_path
        and artifact_paths == record.artifact_paths
    ):
        return record
    return replace(
        record,
        success_marker_path=success_marker_path,
        artifact_paths=artifact_paths,
    )


def _live_session_matches(
    record: LocalJobContinuationRecord,
    live_evidence: LocalJobLiveEvidence | None,
) -> bool:
    if live_evidence is None:
        return False
    return (
        bool(live_evidence.session_id.strip())
        and live_evidence.session_id == record.session_id
        and bool(live_evidence.progress_excerpt.strip())
    )


def _validate_record(record: LocalJobContinuationRecord) -> None:
    _safe_job_id(record.job_id)
    if not record.command or any(not isinstance(part, str) or not part for part in record.command):
        raise ValueError("local job continuation command is required")
    for field_name in ("cwd", "log_path", "session_id"):
        value = getattr(record, field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"local job continuation {field_name} is required")
    if record.status not in JOB_STATUSES:
        raise ValueError("unsupported local job continuation status")
    if record.followup_status not in FOLLOWUP_STATUSES:
        raise ValueError("unsupported local job continuation followup status")
    _optional_int(record.exit_status, "exit_status")
    _optional_int(record.timeout_seconds, "timeout_seconds")
    _optional_int(record.revision, "revision")
    if record.revision < 0:
        raise ValueError("local job continuation revision must be non-negative")
    if record.timeout_seconds is not None and record.timeout_seconds < 0:
        raise ValueError("local job continuation timeout must be non-negative")
    for field_name in ("followup_session_id", "followed_up_at", "success_marker_path"):
        if not isinstance(getattr(record, field_name), str):
            raise ValueError(f"local job continuation {field_name} must be a string")
    if any(not isinstance(path, str) for path in record.artifact_paths):
        raise ValueError("local job continuation artifact paths must be strings")


def _required_text(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _required_runtime_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _required_list(payload: dict[str, Any], field_name: str) -> Sequence[Any]:
    value = payload.get(field_name)
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list")
    return value


def _required_text_list(payload: dict[str, Any], field_name: str) -> list[str]:
    values = _required_list(payload, field_name)
    if any(not isinstance(value, str) or not value for value in values):
        raise ValueError(f"{field_name} must be a non-empty list of strings")
    return list(values)


def _optional_text_list(payload: dict[str, Any], field_name: str) -> list[str]:
    value = payload.get(field_name, [])
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    if any(not isinstance(part, str) for part in value):
        raise ValueError(f"{field_name} must be a list of strings")
    return list(value)


def _optional_text(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name, "")
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value


def _optional_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer or null")
    return value


def _safe_job_id(job_id: str) -> str:
    if not isinstance(job_id, str) or not job_id.strip():
        raise ValueError("local job continuation job_id is required")
    normalized = job_id.strip()
    if normalized in {".", ".."} or JOB_ID_PATTERN.fullmatch(normalized) is None:
        raise ValueError("local job continuation job_id must be path-safe")
    return normalized


def _process_is_active(pid: int) -> bool:
    if os.name == "nt":
        return True
    try:
        os.kill(pid, 0)
    except ValueError:
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as exc:
        return exc.errno == EPERM
    return True


__all__ = [
    "FOLLOWUP_STATUSES",
    "JOB_STATUSES",
    "RECEIPT_SCHEMA_VERSION",
    "RECORD_SCHEMA_VERSION",
    "LocalJobContinuationAdmissionError",
    "LocalJobContinuationFollowupCandidate",
    "LocalJobContinuationFollowupClaim",
    "LocalJobContinuationFollowupClaimBatch",
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
