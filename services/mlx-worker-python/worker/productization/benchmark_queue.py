from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


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
        return BenchmarkQueueRecord(
            queue_item_id=str(payload["queue_item_id"]),
            job_kind=str(payload["job_kind"]),
            model_id=str(payload["model_id"]),
            suite_ids=tuple(str(item) for item in payload.get("suite_ids", [])),
            parameters={str(key): str(value) for key, value in dict(payload.get("parameters", {})).items()},
            status=str(payload["status"]),
            created_at_unix_ms=int(payload["created_at_unix_ms"]),
            updated_at_unix_ms=int(payload["updated_at_unix_ms"]),
            started_at_unix_ms=int(payload.get("started_at_unix_ms", 0)),
            completed_at_unix_ms=int(payload.get("completed_at_unix_ms", 0)),
        )


class BenchmarkQueueStore:
    def enqueue(
        self,
        *,
        queue_root: Path,
        record: BenchmarkQueueRecord,
    ) -> BenchmarkQueueRecord:
        self._write_record(queue_root=queue_root, record=record)
        return record

    def list_records(self, *, queue_root: Path) -> list[BenchmarkQueueRecord]:
        if not queue_root.exists():
            return []

        records = [
            BenchmarkQueueRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
            for path in queue_root.glob("*.json")
            if path.is_file()
        ]
        return sorted(records, key=lambda record: (record.created_at_unix_ms, record.queue_item_id))

    def transition(
        self,
        *,
        queue_root: Path,
        queue_item_id: str,
        status: str,
        updated_at_unix_ms: int,
    ) -> BenchmarkQueueRecord:
        path = self._record_path(queue_root=queue_root, queue_item_id=queue_item_id)
        payload = json.loads(path.read_text(encoding="utf-8"))
        record = BenchmarkQueueRecord.from_dict(payload)
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
        return updated

    def _write_record(self, *, queue_root: Path, record: BenchmarkQueueRecord) -> None:
        queue_root.mkdir(parents=True, exist_ok=True)
        self._record_path(queue_root=queue_root, queue_item_id=record.queue_item_id).write_text(
            json.dumps(record.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )

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
    def _record_path(*, queue_root: Path, queue_item_id: str) -> Path:
        return queue_root / f"{queue_item_id}.json"
