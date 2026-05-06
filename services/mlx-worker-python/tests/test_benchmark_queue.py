from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

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


def test_list_records_skips_entries_when_stat_raises_oserror(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = BenchmarkQueueStore()
    queue_root = tmp_path / "queue"
    queue_root.mkdir()

    class BrokenEntry:
        name = "broken.json"

        def stat(self):
            raise OSError("transient stat failure")

    class BrokenScandir:
        def __enter__(self):
            return iter([BrokenEntry()])

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

    monkeypatch.setattr("worker.productization.benchmark_queue.os.scandir", lambda path: BrokenScandir())

    records = store.list_records(queue_root=queue_root)

    assert records == []


def test_list_records_returns_empty_when_scandir_raises_oserror(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = BenchmarkQueueStore()
    queue_root = tmp_path / "queue"
    queue_root.mkdir()
    monkeypatch.setattr(
        "worker.productization.benchmark_queue.os.scandir",
        lambda path: (_ for _ in ()).throw(OSError("directory unavailable")),
    )

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


def test_list_records_reuses_cached_decoded_records_for_unchanged_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    queue_root = tmp_path / "queue"
    queue_root.mkdir()
    payload = BenchmarkQueueRecord(
        queue_item_id="queue-1",
        job_kind="benchmark",
        model_id="melix-dev-text",
        suite_ids=("smoke",),
        parameters={"sample_size": "32"},
        status="queued",
        created_at_unix_ms=100,
        updated_at_unix_ms=100,
    ).to_dict()
    (queue_root / "queue-1.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")
    store = BenchmarkQueueStore()
    loads = 0
    original_loads = json.loads

    def tracked_loads(raw: str, *args: object, **kwargs: object) -> object:
        nonlocal loads
        loads += 1
        return original_loads(raw, *args, **kwargs)

    monkeypatch.setattr("worker.productization.benchmark_queue.json.loads", tracked_loads)

    first = store.list_records(queue_root=queue_root)
    second = store.list_records(queue_root=queue_root)

    assert [record.queue_item_id for record in first] == ["queue-1"]
    assert [record.queue_item_id for record in second] == ["queue-1"]
    assert loads == 1


def test_list_records_warm_cache_uses_direntry_string_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    queue_root = tmp_path / "queue"
    queue_root.mkdir()
    payload = BenchmarkQueueRecord(
        queue_item_id="queue-1",
        job_kind="benchmark",
        model_id="melix-dev-text",
        suite_ids=("smoke",),
        parameters={"sample_size": "32"},
        status="queued",
        created_at_unix_ms=100,
        updated_at_unix_ms=100,
    ).to_dict()
    (queue_root / "queue-1.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")
    store = BenchmarkQueueStore()

    first = store.list_records(queue_root=queue_root)

    path_constructions = 0
    original_path = Path

    def tracked_path(*args: object, **kwargs: object) -> Path:  # pragma: no cover
        nonlocal path_constructions  # pragma: no cover
        path_constructions += 1  # pragma: no cover
        return original_path(*args, **kwargs)  # pragma: no cover

    monkeypatch.setattr("worker.productization.benchmark_queue.Path", tracked_path)

    second = store.list_records(queue_root=queue_root)

    assert [record.queue_item_id for record in first] == ["queue-1"]
    assert [record.queue_item_id for record in second] == ["queue-1"]
    assert path_constructions == 0


def test_list_records_decodes_uncached_records_from_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    queue_root = tmp_path / "queue"
    queue_root.mkdir()
    payload = BenchmarkQueueRecord(
        queue_item_id="queue-1",
        job_kind="benchmark",
        model_id="melix-dev-text",
        suite_ids=("smoke",),
        parameters={"sample_size": "32"},
        status="queued",
        created_at_unix_ms=100,
        updated_at_unix_ms=100,
    ).to_dict()
    path = queue_root / "queue-1.json"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    store = BenchmarkQueueStore()
    read_bytes_calls = 0
    original_read_bytes = Path.read_bytes

    def tracked_read_bytes(self: Path) -> bytes:
        nonlocal read_bytes_calls
        if self == path:
            read_bytes_calls += 1
        return original_read_bytes(self)

    read_text_mock = Mock(side_effect=AssertionError("uncached queue records should be decoded from bytes"))

    monkeypatch.setattr(Path, "read_bytes", tracked_read_bytes)
    monkeypatch.setattr(Path, "read_text", read_text_mock)

    records = store.list_records(queue_root=queue_root)

    assert [record.queue_item_id for record in records] == ["queue-1"]
    assert read_bytes_calls == 1
    read_text_mock.assert_not_called()


def test_list_records_reuses_direntry_stat_for_metadata_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    queue_root = tmp_path / "queue"
    queue_root.mkdir()
    payload = BenchmarkQueueRecord(
        queue_item_id="queue-1",
        job_kind="benchmark",
        model_id="melix-dev-text",
        suite_ids=("smoke",),
        parameters={"sample_size": "32"},
        status="queued",
        created_at_unix_ms=100,
        updated_at_unix_ms=100,
    ).to_dict()
    path = queue_root / "queue-1.json"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    store = BenchmarkQueueStore()
    original_stat = Path.stat
    record_path_stat_calls = 0

    def tracked_record_path_stat(self: Path, *args: object, **kwargs: object):
        nonlocal record_path_stat_calls
        if self == path:  # pragma: no cover - regression path must stay uncalled
            record_path_stat_calls += 1
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", tracked_record_path_stat)

    records = store.list_records(queue_root=queue_root)

    assert [record.queue_item_id for record in records] == ["queue-1"]
    assert record_path_stat_calls == 0


def test_list_records_cold_cache_miss_clones_only_at_public_return_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    queue_root = tmp_path / "queue"
    queue_root.mkdir()
    payload = BenchmarkQueueRecord(
        queue_item_id="queue-1",
        job_kind="benchmark",
        model_id="melix-dev-text",
        suite_ids=("smoke",),
        parameters={"sample_size": "32"},
        status="queued",
        created_at_unix_ms=100,
        updated_at_unix_ms=100,
    ).to_dict()
    (queue_root / "queue-1.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")
    store = BenchmarkQueueStore()
    clone_calls = 0
    original_clone = BenchmarkQueueStore._clone_record

    def tracked_clone(record: BenchmarkQueueRecord) -> BenchmarkQueueRecord:
        nonlocal clone_calls
        clone_calls += 1
        return original_clone(record)

    monkeypatch.setattr(BenchmarkQueueStore, "_clone_record", staticmethod(tracked_clone))

    records = store.list_records(queue_root=queue_root)

    assert [record.queue_item_id for record in records] == ["queue-1"]
    assert clone_calls == 1


def test_list_records_reload_changed_files_and_transition_refreshes_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    queue_root = tmp_path / "queue"
    queue_root.mkdir()
    path = queue_root / "queue-1.json"
    initial_payload = BenchmarkQueueRecord(
        queue_item_id="queue-1",
        job_kind="benchmark",
        model_id="melix-dev-text",
        suite_ids=("smoke",),
        parameters={"sample_size": "32"},
        status="queued",
        created_at_unix_ms=100,
        updated_at_unix_ms=100,
    ).to_dict()
    path.write_text(json.dumps(initial_payload) + "\n", encoding="utf-8")
    store = BenchmarkQueueStore()
    loads = 0
    original_loads = json.loads

    def tracked_loads(raw: str, *args: object, **kwargs: object) -> object:
        nonlocal loads
        loads += 1
        return original_loads(raw, *args, **kwargs)

    monkeypatch.setattr("worker.productization.benchmark_queue.json.loads", tracked_loads)

    first = store.list_records(queue_root=queue_root)
    updated_payload = dict(initial_payload)
    updated_payload["status"] = "running"
    updated_payload["updated_at_unix_ms"] = 150
    path.write_text(json.dumps(updated_payload, indent=2) + "\n", encoding="utf-8")
    reloaded = store.list_records(queue_root=queue_root)
    transitioned = store.transition(
        queue_root=queue_root,
        queue_item_id="queue-1",
        status="completed",
        updated_at_unix_ms=200,
    )
    cached_after_transition = store.list_records(queue_root=queue_root)

    assert first[0].status == "queued"
    assert reloaded[0].status == "running"
    assert transitioned.status == "completed"
    assert cached_after_transition[0].status == "completed"
    assert loads == 2


def test_list_records_and_transition_do_not_observe_mutated_returned_parameters(tmp_path: Path) -> None:
    store = BenchmarkQueueStore()
    queue_root = tmp_path / "queue"
    enqueued = store.enqueue(
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

    enqueued.parameters["sample_size"] = "999"
    first_read = store.list_records(queue_root=queue_root)
    first_read[0].parameters["batch_factor"] = "4"
    second_read = store.list_records(queue_root=queue_root)
    transitioned = store.transition(
        queue_root=queue_root,
        queue_item_id="queue-1",
        status="running",
        updated_at_unix_ms=150,
    )
    persisted = json.loads((queue_root / "queue-1.json").read_text(encoding="utf-8"))

    assert first_read[0].parameters == {"sample_size": "32", "batch_factor": "4"}
    assert second_read[0].parameters == {"sample_size": "32"}
    assert transitioned.parameters == {"sample_size": "32"}
    assert persisted["parameters"] == {"sample_size": "32"}
