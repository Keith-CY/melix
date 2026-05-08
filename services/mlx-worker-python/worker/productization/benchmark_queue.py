from __future__ import annotations

import json
import os
from dataclasses import dataclass
from operator import attrgetter
from pathlib import Path
import stat


_RECORD_SORT_KEY = attrgetter("created_at_unix_ms", "queue_item_id")


@dataclass(frozen=True)
class _RecordCacheEntry:
    metadata_key: tuple[int, int, int, int]
    record: BenchmarkQueueRecord


@dataclass(frozen=True)
class BenchmarkQueueRecord:
    queue_item_id: str
    job_kind: str
    model_id: str
    suite_ids: tuple[str, ...]
    parameters: dict[str, str]
    status: str
    created_at_unix_ms: int
    updated_at_unix_ms: int
    started_at_unix_ms: int = 0
    completed_at_unix_ms: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "queue_item_id": self.queue_item_id,
            "job_kind": self.job_kind,
            "model_id": self.model_id,
            "suite_ids": list(self.suite_ids),
            "parameters": dict(self.parameters),
            "status": self.status,
            "created_at_unix_ms": self.created_at_unix_ms,
            "updated_at_unix_ms": self.updated_at_unix_ms,
            "started_at_unix_ms": self.started_at_unix_ms,
            "completed_at_unix_ms": self.completed_at_unix_ms,
        }

    @staticmethod
    def from_dict(payload: dict[str, object]) -> BenchmarkQueueRecord:
        raw_suite_ids = payload.get("suite_ids", ())
        raw_parameters = payload.get("parameters", {})
        parameter_items = (
            raw_parameters.items()
            if isinstance(raw_parameters, dict)
            else dict(raw_parameters).items()
        )
        return BenchmarkQueueRecord(
            queue_item_id=str(payload["queue_item_id"]),
            job_kind=str(payload["job_kind"]),
            model_id=str(payload["model_id"]),
            suite_ids=tuple(map(str, raw_suite_ids)),
            parameters={str(key): str(value) for key, value in parameter_items},
            status=str(payload["status"]),
            created_at_unix_ms=int(payload["created_at_unix_ms"]),
            updated_at_unix_ms=int(payload["updated_at_unix_ms"]),
            started_at_unix_ms=int(payload.get("started_at_unix_ms", 0)),
            completed_at_unix_ms=int(payload.get("completed_at_unix_ms", 0)),
        )


class BenchmarkQueueStore:
    def __init__(self) -> None:
        self._decoded_record_cache: dict[str, _RecordCacheEntry] = {}

    def enqueue(
        self,
        *,
        queue_root: Path,
        record: BenchmarkQueueRecord,
    ) -> BenchmarkQueueRecord:
        persisted_record = self._clone_record(record)
        self._write_record(queue_root=queue_root, record=persisted_record)
        return self._clone_record(persisted_record)

    def list_records(self, *, queue_root: Path) -> list[BenchmarkQueueRecord]:
        if not queue_root.is_dir():
            return []

        records = []
        try:
            with os.scandir(queue_root) as entries:
                for entry in entries:
                    if not entry.name.endswith(".json"):
                        continue
                    try:
                        stat_result = entry.stat()
                    except OSError:
                        continue
                    if not stat.S_ISREG(stat_result.st_mode):
                        continue
                    records.append(
                        self._load_record(
                            entry.path,
                            metadata_key=self._metadata_key_from_stat(stat_result),
                        )
                    )
        except OSError:
            return []
        records.sort(key=_RECORD_SORT_KEY)
        return [self._clone_record(record) for record in records]

    def transition(
        self,
        *,
        queue_root: Path,
        queue_item_id: str,
        status: str,
        updated_at_unix_ms: int,
    ) -> BenchmarkQueueRecord:
        path = self._record_path(queue_root=queue_root, queue_item_id=queue_item_id)
        record = self._load_record(path)
        started_at_unix_ms = record.started_at_unix_ms
        if status == "running" and started_at_unix_ms == 0:
            started_at_unix_ms = updated_at_unix_ms
        completed_at_unix_ms = updated_at_unix_ms if status in {"completed", "failed"} else 0
        updated = BenchmarkQueueRecord(
            queue_item_id=record.queue_item_id,
            job_kind=record.job_kind,
            model_id=record.model_id,
            suite_ids=record.suite_ids,
            parameters=record.parameters,
            status=status,
            created_at_unix_ms=record.created_at_unix_ms,
            updated_at_unix_ms=updated_at_unix_ms,
            started_at_unix_ms=started_at_unix_ms,
            completed_at_unix_ms=completed_at_unix_ms,
        )
        self._write_record(queue_root=queue_root, record=updated)
        return self._clone_record(updated)

    def _write_record(self, *, queue_root: Path, record: BenchmarkQueueRecord) -> None:
        queue_root.mkdir(parents=True, exist_ok=True)
        path = self._record_path(queue_root=queue_root, queue_item_id=record.queue_item_id)
        persisted_record = self._clone_record(record)
        path.write_text(
            json.dumps(persisted_record.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )
        self._decoded_record_cache[os.fspath(path)] = _RecordCacheEntry(
            metadata_key=self._metadata_key(path),
            record=persisted_record,
        )

    def _load_record(
        self,
        path: Path | str,
        *,
        metadata_key: tuple[int, int, int, int] | None = None,
    ) -> BenchmarkQueueRecord:
        cache_key = os.fspath(path)
        current_metadata_key = (
            self._metadata_key(Path(path)) if metadata_key is None else metadata_key
        )
        cached = self._decoded_record_cache.get(cache_key)
        if cached is not None and cached.metadata_key == current_metadata_key:
            return cached.record
        record = BenchmarkQueueRecord.from_dict(json.loads(Path(path).read_bytes()))
        self._decoded_record_cache[cache_key] = _RecordCacheEntry(
            metadata_key=current_metadata_key,
            record=record,
        )
        return record

    def queue_snapshot(self, *, queue_root: Path) -> dict[str, object]:
        records = self.list_records(queue_root=queue_root)
        by_status: dict[str, int] = {}
        for record in records:
            by_status[record.status] = by_status.get(record.status, 0) + 1
        return {
            "total": len(records),
            "by_status": by_status,
            "records": [record.to_dict() for record in records],
        }

    @staticmethod
    def _clone_record(record: BenchmarkQueueRecord) -> BenchmarkQueueRecord:
        return BenchmarkQueueRecord(
            queue_item_id=record.queue_item_id,
            job_kind=record.job_kind,
            model_id=record.model_id,
            suite_ids=record.suite_ids,
            parameters=dict(record.parameters),
            status=record.status,
            created_at_unix_ms=record.created_at_unix_ms,
            updated_at_unix_ms=record.updated_at_unix_ms,
            started_at_unix_ms=record.started_at_unix_ms,
            completed_at_unix_ms=record.completed_at_unix_ms,
        )

    @staticmethod
    def _record_path(*, queue_root: Path, queue_item_id: str) -> Path:
        return queue_root / f"{queue_item_id}.json"

    @staticmethod
    def _metadata_key(path: Path) -> tuple[int, int, int, int]:
        return BenchmarkQueueStore._metadata_key_from_stat(path.stat())

    @staticmethod
    def _metadata_key_from_stat(stat_result: os.stat_result) -> tuple[int, int, int, int]:
        return (
            int(stat_result.st_mtime_ns),
            int(stat_result.st_size),
            int(stat_result.st_ino),
            int(stat_result.st_dev),
        )
