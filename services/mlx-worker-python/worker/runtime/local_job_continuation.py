from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass, replace
from errno import EPERM
from pathlib import Path
from typing import Any, Iterator, Sequence
from uuid import uuid4


RECORD_SCHEMA_VERSION = "melix.local_job_continuation_record.v1"
RECEIPT_SCHEMA_VERSION = "melix.local_job_continuation_receipt.v1"

JOB_STATUSES = frozenset({"pending", "running", "completed", "failed", "timeout", "blocked"})
FOLLOWUP_STATUSES = frozenset({"not_started", "pending", "in_progress", "completed", "blocked"})
JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


class LocalJobContinuationStoreError(RuntimeError):
    def __init__(self, message: str, *, receipt: dict[str, Any]) -> None:
        super().__init__(message)
        self.receipt = receipt


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
            return LocalJobContinuationReconciliation(
                record=record,
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
) -> dict[str, Any]:
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "job_id": job_id,
        "status": status,
        "reason": reason,
        "session_id": session_id,
        "exit_status": exit_status,
        "followup_status": followup_status,
        "duplicate_launch_refused": duplicate_launch_refused,
        "completion_evidence_available": completion_evidence_available,
        "corrective_action": corrective_action,
    }


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
    "LocalJobContinuationRecord",
    "LocalJobContinuationReconciliation",
    "LocalJobContinuationStore",
    "LocalJobContinuationStoreError",
    "LocalJobLiveEvidence",
    "reconcile_local_job_continuation",
]
