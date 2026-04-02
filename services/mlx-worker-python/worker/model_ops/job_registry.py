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

    def set_output_dir(self, job_id: str, output_dir: str) -> None:
        with self._lock:
            self._jobs[job_id].output_dir = output_dir

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
            "derived_models": self._derived_model_registry(jobs),
            "downloads": self._download_registry(jobs),
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
        activation_by_hash: dict[str, dict[str, Any]] = {}
        activation_by_path: dict[str, dict[str, Any]] = {}

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

        for job in jobs:
            if job["operation"] != "activate_adapter" or job["status"] != "completed":
                continue
            manifest = job.get("manifest") or {}
            activation = {
                "job_id": job["job_id"],
                "derived_model_id": str(manifest.get("derived_model_id", "")),
                "derived_model_path": str(manifest.get("derived_model_path", "")),
                "derived_model_alias": str(manifest.get("derived_model_alias", "")),
                "activation_duration_ms": float(manifest.get("activation_duration_ms", 0.0)),
                "adapter_manifest_path": str(manifest.get("adapter_manifest_path", "")),
                "source_adapter_job_id": str(manifest.get("source_adapter_job_id", "")),
                "status": "activated",
            }
            adapter_set_hash = str(manifest.get("adapter_set_hash", ""))
            adapter_manifest_path = str(manifest.get("adapter_manifest_path", ""))
            if adapter_set_hash:
                activation_by_hash[adapter_set_hash] = activation
            if adapter_manifest_path:
                activation_by_path[adapter_manifest_path] = activation

        adapters: list[dict[str, Any]] = []
        for job in jobs:
            if job["operation"] != "train_lora" or job["status"] != "completed":
                continue

            manifest = job.get("manifest") or {}
            adapter_name = str(manifest.get("adapter_name", ""))
            output_path = str(job.get("output_path", ""))
            adapter_set_hash = str(manifest.get("adapter_set_hash", ""))
            publish = publish_by_path.get(output_path) or publish_by_name.get(adapter_name)
            activation = activation_by_path.get(output_path) or activation_by_hash.get(adapter_set_hash)

            if publish:
                status = "published"
            elif activation:
                status = "activated"
            else:
                status = job["status"]

            adapters.append(
                {
                    "adapter_id": f"{adapter_name or 'adapter'}@{job['job_id']}",
                    "job_id": job["job_id"],
                    "adapter_name": adapter_name,
                    "source_model": job["source_model"],
                    "dataset_uri": str(manifest.get("dataset_uri", "")),
                    "dataset_source_kind": str(manifest.get("dataset_source_kind", "")),
                    "dataset_id": str(manifest.get("dataset_id", "")),
                    "dataset_format": str(manifest.get("dataset_format", "")),
                    "dataset_version": str(manifest.get("dataset_version", "")),
                    "dataset_sample_count": int(manifest.get("dataset_sample_count", 0)),
                    "dataset_source_manifest_path": str(manifest.get("dataset_source_manifest_path", "")),
                    "dataset_materialized_package_path": str(manifest.get("dataset_materialized_package_path", "")),
                    "dataset_cache_key": str(manifest.get("dataset_cache_key", "")),
                    "dataset_cache_hit": bool(manifest.get("dataset_cache_hit", False)),
                    "normalized_dataset_manifest_path": str(manifest.get("normalized_dataset_manifest_path", "")),
                    "hf_dataset_path": str(manifest.get("hf_dataset_path", "")),
                    "hf_dataset_name": str(manifest.get("hf_dataset_name", "")),
                    "hf_dataset_revision": str(manifest.get("hf_dataset_revision", "")),
                    "hf_train_split": str(manifest.get("hf_train_split", "")),
                    "output_path": output_path,
                    "adapter_set_hash": adapter_set_hash,
                    "target_repo": str(manifest.get("target_repo", "")),
                    "published_repo": publish["target_repo"] if publish else "",
                    "publish_job_id": publish["job_id"] if publish else "",
                    "status": status,
                    "activation_status": activation["status"] if activation else "pending_activation",
                    "derived_model_id": activation["derived_model_id"] if activation else "",
                    "derived_model_path": activation["derived_model_path"] if activation else "",
                    "derived_model_alias": activation["derived_model_alias"] if activation else "",
                    "activation_job_id": activation["job_id"] if activation else "",
                    "adapter_manifest_path": activation["adapter_manifest_path"] if activation else output_path,
                    "source_adapter_job_id": activation["source_adapter_job_id"] if activation else job["job_id"],
                    "activation_duration_ms": activation["activation_duration_ms"] if activation else 0.0,
                    "exportable_state": "ready",
                    "published_state": "published" if publish else "not_published",
                    "response_only": bool(manifest.get("response_only", False)),
                    "gradient_checkpointing": bool(manifest.get("gradient_checkpointing", False)),
                    "training_duration_ms": float(manifest.get("training_duration_ms", 0.0)),
                    "adapter_publish_ms": float(manifest.get("adapter_publish_ms", 0.0)),
                }
            )

        return adapters

    @staticmethod
    def _derived_model_registry(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        derived_models: list[dict[str, Any]] = []
        for job in jobs:
            if job["operation"] != "activate_adapter" or job["status"] != "completed":
                continue
            manifest = job.get("manifest") or {}
            derived_models.append(
                {
                    "job_id": job["job_id"],
                    "model_id": str(manifest.get("derived_model_id", "")),
                    "model_path": str(manifest.get("derived_model_path", "")),
                    "adapter_set_hash": str(manifest.get("adapter_set_hash", "")),
                    "adapter_manifest_path": str(manifest.get("adapter_manifest_path", "")),
                    "adapter_name": str(manifest.get("adapter_name", "")),
                    "derived_model_alias": str(manifest.get("derived_model_alias", "")),
                    "source_adapter_job_id": str(manifest.get("source_adapter_job_id", "")),
                    "source_model": str(manifest.get("source_model", "")),
                    "activation_mode": str(manifest.get("activation_mode", "")),
                    "status": "activated",
                }
            )
        return derived_models

    @staticmethod
    def _download_registry(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        downloads: list[dict[str, Any]] = []
        for job in jobs:
            if job["operation"] != "download":
                continue

            manifest = job.get("manifest") or {}
            downloads.append(
                {
                    "job_id": job["job_id"],
                    "source_model": job["source_model"],
                    "status": str(manifest.get("terminal_state", manifest.get("status", job["status"]))),
                    "stage": str(manifest.get("stage", job["stage"])),
                    "pct": float(manifest.get("pct", job["pct"])),
                    "output_path": str(manifest.get("output_path", job["output_path"])),
                    "partial_path": str(manifest.get("partial_path", "")),
                    "state_path": str(manifest.get("state_path", "")),
                    "selected_mirror": str(manifest.get("selected_mirror", "")),
                    "downloaded_bytes": int(manifest.get("downloaded_bytes", 0)),
                    "total_bytes": int(manifest.get("total_bytes", 0)),
                    "resume_used": bool(manifest.get("resume_used", False)),
                    "resume_from_bytes": int(manifest.get("resume_from_bytes", 0)),
                    "retry_count": int(manifest.get("retry_count", 0)),
                    "stall_detection_count": int(manifest.get("stall_detection_count", 0)),
                    "stall_reason": str(manifest.get("stall_reason", "")),
                }
            )
        return downloads
