from __future__ import annotations

import json
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


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

    def snapshot(self, exclude_job_ids: set[str] | None = None) -> dict[str, Any]:
        excluded = exclude_job_ids or set()
        with self._lock:
            jobs = [
                self._snapshot_job(job)
                for job in sorted(self._jobs.values(), key=self._job_sort_key, reverse=True)
                if job.job_id not in excluded
            ]
        return {
            "jobs": jobs,
            "adapters": self._adapter_registry(jobs),
        }

    @staticmethod
    def _job_sort_key(job: ModelOpsJob) -> int:
        try:
            return int(job.job_id.rsplit("-", maxsplit=1)[-1])
        except ValueError:
            return 0

    @staticmethod
    def _snapshot_job(job: ModelOpsJob) -> dict[str, Any]:
        stage, pct = ("queued", 0.0)
        if job.stage_history:
            stage, pct = job.stage_history[-1]

        manifest: dict[str, Any] = {}
        if job.manifest_json:
            try:
                decoded = json.loads(job.manifest_json)
            except json.JSONDecodeError:
                decoded = {}
            if isinstance(decoded, dict):
                manifest = decoded

        return {
            "job_id": job.job_id,
            "operation": job.operation,
            "source_model": job.source_model,
            "output_dir": job.output_dir,
            "status": job.status,
            "stage": stage,
            "pct": pct,
            "output_path": job.output_path,
            "error_code": job.error_code,
            "error_message": job.error_message,
            "stage_history": [
                {"stage": stage_name, "pct": stage_pct}
                for stage_name, stage_pct in job.stage_history
            ],
            "manifest": manifest,
        }

    @staticmethod
    def _adapter_registry(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        publish_by_name: dict[str, dict[str, Any]] = {}
        publish_by_path: dict[str, dict[str, Any]] = {}

        for job in jobs:
            if job["operation"] != "upload" or job["status"] != "completed":
                continue
            manifest = job.get("manifest") or {}
            ext = manifest.get("ext") if isinstance(manifest.get("ext"), dict) else {}
            artifact_kind = str(ext.get("artifact_kind", manifest.get("artifact_kind", "")))
            if artifact_kind != "adapter":
                continue

            publish = {
                "job_id": job["job_id"],
                "target_repo": str(manifest.get("target_repo", ext.get("target_repo", ""))),
            }
            adapter_name = str(ext.get("adapter_name", manifest.get("adapter_name", "")))
            artifact_path = str(ext.get("artifact_path", manifest.get("artifact_path", "")))
            if adapter_name:
                publish_by_name[adapter_name] = publish
            if artifact_path:
                publish_by_path[artifact_path] = publish

        adapters: list[dict[str, Any]] = []
        for job in jobs:
            if job["operation"] != "train_lora" or job["status"] != "completed":
                continue

            manifest = job.get("manifest") or {}
            adapter_name = str(manifest.get("adapter_name", ""))
            output_path = str(job.get("output_path", ""))
            publish = publish_by_path.get(output_path) or publish_by_name.get(adapter_name)

            adapters.append(
                {
                    "adapter_id": f"{adapter_name or 'adapter'}@{job['job_id']}",
                    "job_id": job["job_id"],
                    "adapter_name": adapter_name,
                    "source_model": job["source_model"],
                    "dataset_uri": str(manifest.get("dataset_uri", "")),
                    "output_path": output_path,
                    "target_repo": str(manifest.get("target_repo", "")),
                    "published_repo": publish["target_repo"] if publish else "",
                    "publish_job_id": publish["job_id"] if publish else "",
                    "status": "published" if publish else job["status"],
                    "training_duration_ms": float(manifest.get("training_duration_ms", 0.0)),
                    "adapter_publish_ms": float(manifest.get("adapter_publish_ms", 0.0)),
                }
            )

        return adapters
