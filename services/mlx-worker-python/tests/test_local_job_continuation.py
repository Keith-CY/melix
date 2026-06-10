from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from worker.runtime.local_job_continuation import (
    RECEIPT_SCHEMA_VERSION,
    RECORD_SCHEMA_VERSION,
    LocalJobContinuationRecord,
    LocalJobContinuationStore,
    LocalJobContinuationStoreError,
    LocalJobLiveEvidence,
    reconcile_local_job_continuation,
)


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
