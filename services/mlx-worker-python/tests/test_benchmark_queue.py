from __future__ import annotations

import json
from pathlib import Path

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
