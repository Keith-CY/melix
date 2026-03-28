from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock


@dataclass
class ModelOpsJob:
    job_id: str
    operation: str
    source_model: str
    output_dir: str
    stage_history: list[tuple[str, float]] = field(default_factory=list)
    manifest_json: str = ""
    output_path: str = ""
    status: str = "running"
    error_code: str = ""
    error_message: str = ""


class ModelOpsJobRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._next_id = 1
        self._jobs: dict[str, ModelOpsJob] = {}

    def start(self, operation: str, source_model: str, output_dir: str) -> ModelOpsJob:
        with self._lock:
            job_id = f"model-ops-{self._next_id:04d}"
            self._next_id += 1
            job = ModelOpsJob(
                job_id=job_id,
                operation=operation,
                source_model=source_model,
                output_dir=output_dir,
            )
            self._jobs[job_id] = job
            return job

    def progress(self, job_id: str, stage: str, pct: float) -> None:
        with self._lock:
            self._jobs[job_id].stage_history.append((stage, pct))

    def attach_manifest(self, job_id: str, manifest_json: str) -> None:
        with self._lock:
            self._jobs[job_id].manifest_json = manifest_json

    def complete(self, job_id: str, output_path: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "completed"
            job.output_path = output_path

    def fail(self, job_id: str, code: str, message: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "failed"
            job.error_code = code
            job.error_message = message
