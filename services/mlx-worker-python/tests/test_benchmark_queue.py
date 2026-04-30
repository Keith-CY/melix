from __future__ import annotations

import json
from pathlib import Path

import pytest

from worker.productization.benchmark_queue import (
    BenchmarkQueueRecord,
    BenchmarkQueueStore,
)


def test_enqueue_persists_benchmark_queue_record_with_parameters(tmp_path: Path) -> None:
    store = BenchmarkQueueStore()

    record = store.enqueue(
        queue_root=tmp_path / "queue",
        record=BenchmarkQueueRecord(
            queue_item_id="queue-1",
            job_kind="benchmark",
            model_id="melix-dev-text",
            suite_ids=("smoke", "latency"),
            parameters={"sample_size": "32", "batch_factor": "2"},
            status="queued",
            created_at_unix_ms=100,
            updated_at_unix_ms=100,
        ),
    )

    persisted = tmp_path / "queue" / "queue-1.json"
    assert persisted.exists() is True
    assert record.queue_item_id == "queue-1"
    assert json.loads(persisted.read_text(encoding="utf-8")) == record.to_dict()


def test_list_records_is_stable_by_created_time_then_id(tmp_path: Path) -> None:
    store = BenchmarkQueueStore()
    queue_root = tmp_path / "queue"

    store.enqueue(
        queue_root=queue_root,
        record=BenchmarkQueueRecord(
            queue_item_id="queue-b",
            job_kind="evaluation",
            model_id="melix-dev-text",
            suite_ids=("mmlu",),
            parameters={"sample_size": "8"},
            status="queued",
            created_at_unix_ms=200,
            updated_at_unix_ms=200,
        ),
    )
    store.enqueue(
        queue_root=queue_root,
        record=BenchmarkQueueRecord(
            queue_item_id="queue-a",
            job_kind="benchmark",
            model_id="melix-dev-text",
            suite_ids=("smoke",),
            parameters={"sample_size": "16"},
            status="queued",
            created_at_unix_ms=100,
            updated_at_unix_ms=100,
        ),
    )
    store.enqueue(
        queue_root=queue_root,
        record=BenchmarkQueueRecord(
            queue_item_id="queue-c",
            job_kind="benchmark",
            model_id="melix-dev-text",
            suite_ids=("latency",),
            parameters={"sample_size": "16"},
            status="queued",
            created_at_unix_ms=200,
            updated_at_unix_ms=200,
        ),
    )

    records = store.list_records(queue_root=queue_root)

    assert [record.queue_item_id for record in records] == ["queue-a", "queue-b", "queue-c"]


def test_list_records_ignores_non_json_entries_and_json_named_directories(tmp_path: Path) -> None:
    store = BenchmarkQueueStore()
    queue_root = tmp_path / "queue"
    queue_root.mkdir()
    (queue_root / "notes.txt").write_text("ignore me", encoding="utf-8")
    (queue_root / "nested-record.json").mkdir()

    store.enqueue(
        queue_root=queue_root,
        record=BenchmarkQueueRecord(
            queue_item_id="queue-valid",
            job_kind="benchmark",
            model_id="melix-dev-text",
            suite_ids=("smoke",),
            parameters={},
            status="queued",
            created_at_unix_ms=100,
            updated_at_unix_ms=100,
        ),
    )

    records = store.list_records(queue_root=queue_root)

    assert [record.queue_item_id for record in records] == ["queue-valid"]


def test_queue_snapshot_returns_counts_and_records_by_status(tmp_path: Path) -> None:
    store = BenchmarkQueueStore()
    queue_root = tmp_path / "queue"

    store.enqueue(
        queue_root=queue_root,
        record=BenchmarkQueueRecord(
            queue_item_id="queue-1",
            job_kind="benchmark",
            model_id="melix-dev-text",
            suite_ids=("smoke",),
            parameters={"sample_size": "32"},
            status="queued",
            created_at_unix_ms=100,
            updated_at_unix_ms=100,
        ),
    )
    store.enqueue(
        queue_root=queue_root,
        record=BenchmarkQueueRecord(
            queue_item_id="queue-2",
            job_kind="evaluation",
            model_id="melix-dev-text",
            suite_ids=("mmlu",),
            parameters={"sample_size": "8"},
            status="queued",
            created_at_unix_ms=200,
            updated_at_unix_ms=200,
        ),
    )
    store.transition(
        queue_root=queue_root,
        queue_item_id="queue-1",
        status="running",
        updated_at_unix_ms=150,
    )
    store.transition(
        queue_root=queue_root,
        queue_item_id="queue-1",
        status="completed",
        updated_at_unix_ms=300,
    )

    snapshot = store.queue_snapshot(queue_root=queue_root)

    assert snapshot["total"] == 2
    assert snapshot["by_status"] == {"completed": 1, "queued": 1}
    assert len(snapshot["records"]) == 2
    assert snapshot["records"][0]["queue_item_id"] == "queue-1"
    assert snapshot["records"][0]["status"] == "completed"
    assert snapshot["records"][0]["parameters"] == {"sample_size": "32"}
    assert snapshot["records"][1]["queue_item_id"] == "queue-2"
    assert snapshot["records"][1]["status"] == "queued"


def test_transition_updates_state_and_terminal_timestamp(tmp_path: Path) -> None:
    store = BenchmarkQueueStore()
    queue_root = tmp_path / "queue"
    store.enqueue(
        queue_root=queue_root,
        record=BenchmarkQueueRecord(
            queue_item_id="queue-1",
            job_kind="benchmark",
            model_id="melix-dev-text",
            suite_ids=("smoke",),
            parameters={"sample_size": "32", "batch_factor": "2"},
            status="queued",
            created_at_unix_ms=100,
            updated_at_unix_ms=100,
        ),
    )

    running = store.transition(
        queue_root=queue_root,
        queue_item_id="queue-1",
        status="running",
        updated_at_unix_ms=150,
    )
    completed = store.transition(
        queue_root=queue_root,
        queue_item_id="queue-1",
        status="completed",
        updated_at_unix_ms=200,
    )

    assert running.status == "running"
    assert running.updated_at_unix_ms == 150
    assert completed.status == "completed"
    assert completed.updated_at_unix_ms == 200
    assert completed.completed_at_unix_ms == 200
    persisted = json.loads((queue_root / "queue-1.json").read_text(encoding="utf-8"))
    assert persisted["status"] == "completed"
    assert persisted["completed_at_unix_ms"] == 200


def test_transition_raises_when_queue_item_does_not_exist(tmp_path: Path) -> None:
    store = BenchmarkQueueStore()

    with pytest.raises(FileNotFoundError):
        store.transition(
            queue_root=tmp_path / "queue",
            queue_item_id="nonexistent-item",
            status="running",
            updated_at_unix_ms=100,
        )


def test_list_records_returns_empty_when_queue_root_does_not_exist(tmp_path: Path) -> None:
    store = BenchmarkQueueStore()

    records = store.list_records(queue_root=tmp_path / "missing-queue-dir")

    assert records == []


def test_list_records_returns_empty_when_queue_root_is_a_file(tmp_path: Path) -> None:
    store = BenchmarkQueueStore()
    queue_root = tmp_path / "queue-file"
    queue_root.write_text("not a directory", encoding="utf-8")

    records = store.list_records(queue_root=queue_root)

    assert records == []


def test_benchmark_queue_record_from_dict_uses_zero_for_missing_optional_timestamps() -> None:
    payload = {
        "queue_item_id": "q-minimal",
        "job_kind": "benchmark",
        "model_id": "melix-dev-text",
        "status": "queued",
        "created_at_unix_ms": 100,
        "updated_at_unix_ms": 100,
    }

    record = BenchmarkQueueRecord.from_dict(payload)

    assert record.started_at_unix_ms == 0
    assert record.completed_at_unix_ms == 0
    assert record.suite_ids == ()
    assert record.parameters == {}


def test_transition_to_failed_sets_completed_timestamp(tmp_path: Path) -> None:
    store = BenchmarkQueueStore()
    queue_root = tmp_path / "queue"
    store.enqueue(
        queue_root=queue_root,
        record=BenchmarkQueueRecord(
            queue_item_id="queue-fail",
            job_kind="benchmark",
            model_id="melix-dev-text",
            suite_ids=("smoke",),
            parameters={},
            status="queued",
            created_at_unix_ms=100,
            updated_at_unix_ms=100,
        ),
    )

    failed = store.transition(
        queue_root=queue_root,
        queue_item_id="queue-fail",
        status="failed",
        updated_at_unix_ms=200,
    )

    assert failed.status == "failed"
    assert failed.completed_at_unix_ms == 200
    persisted = json.loads((queue_root / "queue-fail.json").read_text(encoding="utf-8"))
    assert persisted["status"] == "failed"
    assert persisted["completed_at_unix_ms"] == 200


def test_transition_running_does_not_overwrite_existing_started_at(tmp_path: Path) -> None:
    store = BenchmarkQueueStore()
    queue_root = tmp_path / "queue"
    store.enqueue(
        queue_root=queue_root,
        record=BenchmarkQueueRecord(
            queue_item_id="queue-restart",
            job_kind="benchmark",
            model_id="melix-dev-text",
            suite_ids=("smoke",),
            parameters={},
            status="queued",
            created_at_unix_ms=100,
            updated_at_unix_ms=100,
        ),
    )

    first_run = store.transition(
        queue_root=queue_root,
        queue_item_id="queue-restart",
        status="running",
        updated_at_unix_ms=150,
    )
    second_run = store.transition(
        queue_root=queue_root,
        queue_item_id="queue-restart",
        status="running",
        updated_at_unix_ms=200,
    )

    assert first_run.started_at_unix_ms == 150
    # a second "running" transition must not overwrite the original start time
    assert second_run.started_at_unix_ms == 150
    assert second_run.updated_at_unix_ms == 200


def test_queue_snapshot_returns_empty_for_empty_directory(tmp_path: Path) -> None:
    store = BenchmarkQueueStore()

    snapshot = store.queue_snapshot(queue_root=tmp_path / "empty-queue")

    assert snapshot["total"] == 0
    assert snapshot["by_status"] == {}
    assert snapshot["records"] == []
