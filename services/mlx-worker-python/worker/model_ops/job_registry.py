from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
import math
from pathlib import Path
from threading import Lock
from typing import Any

from packages.protocol.python.worker.v1 import common_pb2

from worker.productization.lora_experiment_store import LoraExperimentStore

ADAPTER_RUNTIME_BASE_REUSE_KEY_FIELD = "adapter_runtime_base_reuse_key"
ADAPTER_RUNTIME_ADAPTER_ISOLATION_KEY_FIELD = "adapter_runtime_adapter_isolation_key"
ADAPTER_RUNTIME_SWITCH_MODE_FIELD = "adapter_runtime_switch_mode"
ADAPTER_RUNTIME_SHARING_POLICY_FIELD = "adapter_runtime_sharing_policy"
ADAPTER_RUNTIME_COMPATIBILITY_STATUS_FIELD = "adapter_runtime_compatibility_status"

_ADAPTER_RUNTIME_BASE_REUSE_MANIFEST_KEY = "adapter_runtime.base_reuse_key"
_ADAPTER_RUNTIME_ADAPTER_ISOLATION_MANIFEST_KEY = "adapter_runtime.adapter_isolation_key"
_ADAPTER_RUNTIME_SWITCH_MODE_MANIFEST_KEY = "adapter_runtime.switch_mode"
_ADAPTER_RUNTIME_SHARING_POLICY_MANIFEST_KEY = "adapter_runtime.sharing_policy"
_ADAPTER_RUNTIME_COMPATIBILITY_STATUS_MANIFEST_KEY = "adapter_runtime.compatibility_status"


def _runtime_mode_from_activation(activation_mode: str) -> int:
    """Map the manifest activation_mode string to a ``RuntimeMode`` enum int.

    The on-disk manifest keeps the string as its canonical form; consumers
    that need the typed enum derive it at read time so the JSON format stays
    decoupled from proto wire encoding. Unknown or empty strings resolve to
    ``RUNTIME_MODE_UNSPECIFIED`` (0).
    """
    normalized = (activation_mode or "").strip()
    if normalized == "adapter_backed_runtime":
        return int(common_pb2.RUNTIME_MODE_ADAPTER_BACKED)
    if normalized == "fused_derived_model":
        return int(common_pb2.RUNTIME_MODE_FUSED_DERIVED_MODEL)
    return int(common_pb2.RUNTIME_MODE_UNSPECIFIED)


@dataclass
class ModelOpsJob:
    job_id: str
    operation: str
    source_model: str
    output_dir: str
    stage_history: list[tuple[str, float]] = field(default_factory=list)
    manifest_json: str = ""
    manifest: dict[str, Any] = field(default_factory=dict)
    manifest_cached: bool = False
    output_path: str = ""
    status: str = "running"
    error_code: str = ""
    error_message: str = ""


@dataclass
class _ActiveDerivedModelLookup:
    job: ModelOpsJob
    manifest: dict[str, Any]
    activation_manifest_path: str
    resolved_activation_manifest_path: str | None = None
    target_payload: dict[str, Any] | None = None


class ModelOpsJobRegistry:
    def __init__(self, jobs_root: str | Path | None = None) -> None:
        self._lock = Lock()
        self._next_id = 1
        self._jobs: dict[str, ModelOpsJob] = {}
        self._active_derived_model_rows_cache: tuple[tuple[ModelOpsJob, dict[str, Any], str], ...] | None = None
        self._active_derived_model_manifests_cache: tuple[dict[str, Any], ...] | None = None
        self._active_derived_model_by_id_cache: dict[str, _ActiveDerivedModelLookup] | None = None
        self._active_derived_model_by_manifest_path_cache: dict[str, _ActiveDerivedModelLookup] | None = None
        self._jobs_root = Path(jobs_root).expanduser().resolve() if jobs_root is not None else None
        self._lora_experiment_store = LoraExperimentStore()
        if self._jobs_root is not None:
            self._restore_from_jobs_root()

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
            self._invalidate_active_derived_model_rows_cache()
            return job

    def progress(self, job_id: str, stage: str, pct: float) -> None:
        with self._lock:
            self._jobs[job_id].stage_history.append((stage, pct))

    def set_output_dir(self, job_id: str, output_dir: str) -> None:
        with self._lock:
            self._jobs[job_id].output_dir = output_dir
            self._invalidate_active_derived_model_rows_cache()

    def attach_manifest(self, job_id: str, manifest_json: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.manifest_json = manifest_json
            job.manifest = self._decode_manifest_json(manifest_json)
            job.manifest_cached = True
            self._invalidate_active_derived_model_rows_cache()

    def complete(self, job_id: str, output_path: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "completed"
            job.output_path = output_path
            self._invalidate_active_derived_model_rows_cache()

    def fail(self, job_id: str, code: str, message: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "failed"
            job.error_code = code
            job.error_message = message
            self._invalidate_active_derived_model_rows_cache()

    def snapshot(self, exclude_job_ids: set[str] | None = None) -> dict[str, Any]:
        excluded = exclude_job_ids or set()
        with self._lock:
            jobs = [
                self._snapshot_job(job)
                for job in sorted(self._jobs.values(), key=self._job_sort_key, reverse=True)
                if job.job_id not in excluded
            ]
        return self._json_safe(
            {
            "jobs": jobs,
            "adapters": self._adapter_registry(jobs),
            "derived_models": self._derived_model_registry(jobs),
            "publishes": self._publish_registry(jobs),
            "downloads": self._download_registry(jobs),
            "experiment_groups": self._experiment_groups(),
            }
        )

    def _restore_from_jobs_root(self) -> None:
        if self._jobs_root is None or self._jobs_root.exists() is False:
            return

        manifest_paths = self._collect_restore_manifest_paths(self._jobs_root)
        self._restore_manifest_jobs(
            operation="train_lora",
            manifest_paths=manifest_paths["train_lora"],
            pct=0.97,
        )
        self._restore_manifest_jobs(
            operation="activate_adapter",
            manifest_paths=manifest_paths["activate_adapter"],
            pct=0.95,
        )
        self._restore_manifest_jobs(
            operation="remove_derived_model",
            manifest_paths=manifest_paths["remove_derived_model"],
            pct=0.95,
        )
        self._next_id = max(self._next_id, self._max_numeric_job_id() + 1)

    @staticmethod
    def _collect_restore_manifest_paths(
        jobs_root: Path,
    ) -> dict[str, list[Path]]:
        manifest_paths: dict[str, list[Path]] = {
            "train_lora": [],
            "activate_adapter": [],
            "remove_derived_model": [],
        }

        try:
            with os.scandir(os.fspath(jobs_root)) as op_entries:
                for op_entry in op_entries:
                    if not op_entry.is_dir(follow_symlinks=False):
                        continue
                    if op_entry.name == "train_lora":
                        manifest_paths["train_lora"].extend(
                            ModelOpsJobRegistry._collect_train_lora_restore_manifests(Path(op_entry.path))
                        )
                    elif op_entry.name == "activate_adapter":
                        manifest_paths["activate_adapter"].extend(
                            ModelOpsJobRegistry._collect_activate_adapter_restore_manifests(
                                Path(op_entry.path)
                            )
                        )
                    elif op_entry.name == "remove_derived_model":
                        manifest_paths["remove_derived_model"].extend(
                            ModelOpsJobRegistry._collect_remove_derived_model_restore_manifests(
                                Path(op_entry.path)
                            )
                        )
        except OSError:
            return manifest_paths

        manifest_paths["train_lora"].sort()
        manifest_paths["activate_adapter"].sort()
        manifest_paths["remove_derived_model"].sort()
        return manifest_paths

    @staticmethod
    def _collect_train_lora_restore_manifests(manifest_root: Path) -> list[Path]:
        manifests: list[Path] = []
        try:
            with os.scandir(os.fspath(manifest_root)) as job_id_entries:
                for job_id_entry in job_id_entries:
                    if (
                        not job_id_entry.is_dir(follow_symlinks=False)
                        or not job_id_entry.name.startswith("model-ops-")
                    ):
                        continue
                    manifest_path = Path(job_id_entry.path) / "train_lora.adapter.json"
                    if manifest_path.is_file():
                        manifests.append(manifest_path)
        except OSError:
            return manifests
        return manifests

    @staticmethod
    def _collect_activate_adapter_restore_manifests(manifest_root: Path) -> list[Path]:
        manifests: list[Path] = []
        try:
            with os.scandir(os.fspath(manifest_root)) as job_id_entries:
                for job_id_entry in job_id_entries:
                    if (
                        not job_id_entry.is_dir(follow_symlinks=False)
                        or not job_id_entry.name.startswith("model-ops-")
                    ):
                        continue
                    try:
                        with os.scandir(os.fspath(job_id_entry.path)) as manifest_entry_parent_entries:
                            for manifest_entry in manifest_entry_parent_entries:
                                if not manifest_entry.is_dir(follow_symlinks=False):
                                    continue
                                manifest_path = Path(manifest_entry.path) / "manifest.json"
                                if manifest_path.is_file():
                                    manifests.append(manifest_path)
                    except OSError:
                        continue
        except OSError:
            return manifests
        return manifests

    @staticmethod
    def _collect_remove_derived_model_restore_manifests(manifest_root: Path) -> list[Path]:
        manifests: list[Path] = []
        try:
            with os.scandir(os.fspath(manifest_root)) as job_id_entries:
                for job_id_entry in job_id_entries:
                    if (
                        not job_id_entry.is_dir(follow_symlinks=False)
                        or not job_id_entry.name.startswith("model-ops-")
                    ):
                        continue
                    manifest_path = Path(job_id_entry.path) / "remove_derived_model.lifecycle.json"
                    if manifest_path.is_file():
                        manifests.append(manifest_path)
        except OSError:
            return manifests
        return manifests

    def _restore_manifest_jobs(
        self,
        *,
        operation: str,
        manifest_paths,
        pct: float,
    ) -> None:
        for manifest_path in manifest_paths:
            payload = self._read_manifest_dict(manifest_path)
            if payload:
                raw_operation = payload.get("operation", "")
                if raw_operation != operation and str(raw_operation).strip() != operation:
                    continue
            else:
                continue

            job_id = self._resolved_job_id(manifest_path, payload)
            if not job_id or job_id in self._jobs:
                continue

            output_dir = self._resolved_output_dir_for_restore(operation, manifest_path)
            self._jobs[job_id] = ModelOpsJob(
                job_id=job_id,
                operation=operation,
                source_model=str(payload.get("source_model", "")),
                output_dir=str(output_dir),
                stage_history=[("write_manifest", pct)],
                manifest=payload,
                manifest_cached=True,
                output_path=str(manifest_path),
                status="completed",
            )

    @staticmethod
    def _decode_manifest_json(manifest_json: str) -> dict[str, Any]:
        try:
            decoded = json.loads(manifest_json)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}

    @staticmethod
    def _read_manifest_dict(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_bytes())
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _resolved_job_id(manifest_path: Path, payload: dict[str, Any]) -> str:
        manifest_job_id = str(payload.get("job_id", "")).strip()
        if manifest_job_id:
            return manifest_job_id

        for candidate in manifest_path.parts[::-1]:
            if candidate.startswith("model-ops-"):
                return candidate
        return ""

    @staticmethod
    def _resolved_output_dir_for_restore(operation: str, manifest_path: Path) -> Path:
        if operation == "activate_adapter":
            return manifest_path.parents[1]
        if operation == "remove_derived_model":
            return manifest_path.parent
        return manifest_path.parent

    def _ordered_jobs(self) -> tuple[ModelOpsJob, ...]:
        with self._lock:
            return tuple(sorted(self._jobs.values(), key=self._job_sort_key, reverse=True))

    def _invalidate_active_derived_model_rows_cache(self) -> None:
        self._active_derived_model_rows_cache = None
        self._active_derived_model_manifests_cache = None
        self._active_derived_model_by_id_cache = None
        self._active_derived_model_by_manifest_path_cache = None

    def _cached_active_derived_model_job_rows(
        self,
    ) -> tuple[tuple[ModelOpsJob, dict[str, Any], str], ...]:
        cached_rows = self._active_derived_model_rows_cache
        if cached_rows is None:
            cached_rows = self._active_derived_model_job_rows(self._ordered_jobs())
            self._active_derived_model_rows_cache = cached_rows
        return cached_rows

    def _cached_active_derived_model_by_id(self) -> dict[str, _ActiveDerivedModelLookup]:
        cached_by_id = self._active_derived_model_by_id_cache
        if cached_by_id is None:
            cached_by_id = {}
            for job, manifest, activation_manifest_path in self._cached_active_derived_model_job_rows():
                candidate_model_id = str(manifest.get("derived_model_id", "")).strip()
                if candidate_model_id and candidate_model_id not in cached_by_id:
                    cached_by_id[candidate_model_id] = _ActiveDerivedModelLookup(
                        job=job,
                        manifest=manifest,
                        activation_manifest_path=activation_manifest_path,
                    )
            self._active_derived_model_by_id_cache = cached_by_id
        return cached_by_id

    def _cached_active_derived_model_by_manifest_path(self) -> dict[str, _ActiveDerivedModelLookup]:
        cached_by_manifest_path = self._active_derived_model_by_manifest_path_cache
        if cached_by_manifest_path is None:
            cached_by_manifest_path = {}
            for job, manifest, activation_manifest_path in self._cached_active_derived_model_job_rows():
                resolved_activation_manifest_path = str(
                    Path(activation_manifest_path).expanduser().resolve()
                )
                if resolved_activation_manifest_path and resolved_activation_manifest_path not in cached_by_manifest_path:
                    cached_by_manifest_path[resolved_activation_manifest_path] = _ActiveDerivedModelLookup(
                        job=job,
                        manifest=manifest,
                        activation_manifest_path=activation_manifest_path,
                        resolved_activation_manifest_path=resolved_activation_manifest_path,
                    )
            self._active_derived_model_by_manifest_path_cache = cached_by_manifest_path
        return cached_by_manifest_path

    @staticmethod
    def _derived_model_target_payload(
        job: ModelOpsJob,
        manifest: dict[str, Any],
        activation_manifest_path: str,
        *,
        resolved_activation_manifest_path: str | None = None,
    ) -> dict[str, Any]:
        if resolved_activation_manifest_path is None:
            resolved_activation_manifest_path = str(Path(activation_manifest_path).expanduser().resolve())
        candidate_model_id = str(manifest.get("derived_model_id", "")).strip()
        target_payload = {
            "activation_job_id": job.job_id,
            "activation_manifest_path": resolved_activation_manifest_path,
            "output_dir": job.output_dir,
            "source_model": str(manifest.get("source_model", "")),
            "derived_model_id": candidate_model_id,
            "derived_model_path": str(manifest.get("derived_model_path", "")),
            "derived_model_alias": str(manifest.get("derived_model_alias", "")),
            "activation_mode": str(manifest.get("activation_mode", "")),
            "runtime_mode": _runtime_mode_from_activation(str(manifest.get("activation_mode", ""))),
            "adapter_manifest_path": str(manifest.get("adapter_manifest_path", "")),
            "adapter_weights_path": str(manifest.get("adapter_weights_path", "")),
        }
        ModelOpsJobRegistry._copy_adapter_runtime_row_fields(target_payload, manifest)
        return target_payload

    @classmethod
    def _cached_derived_model_target_payload(
        cls,
        lookup: _ActiveDerivedModelLookup,
        *,
        resolved_activation_manifest_path: str,
    ) -> dict[str, Any]:
        target_payload = lookup.target_payload
        if target_payload is None:
            target_payload = cls._derived_model_target_payload(
                lookup.job,
                lookup.manifest,
                lookup.activation_manifest_path,
                resolved_activation_manifest_path=resolved_activation_manifest_path,
            )
            lookup.target_payload = target_payload
        return dict(target_payload)

    @staticmethod
    def _copy_adapter_runtime_row_fields(row: dict[str, Any], manifest: dict[str, Any]) -> None:
        if (
            _ADAPTER_RUNTIME_BASE_REUSE_MANIFEST_KEY in manifest
            or _ADAPTER_RUNTIME_ADAPTER_ISOLATION_MANIFEST_KEY in manifest
            or _ADAPTER_RUNTIME_SWITCH_MODE_MANIFEST_KEY in manifest
            or _ADAPTER_RUNTIME_SHARING_POLICY_MANIFEST_KEY in manifest
            or _ADAPTER_RUNTIME_COMPATIBILITY_STATUS_MANIFEST_KEY in manifest
        ):
            row[ADAPTER_RUNTIME_BASE_REUSE_KEY_FIELD] = str(
                manifest.get(_ADAPTER_RUNTIME_BASE_REUSE_MANIFEST_KEY, "")
            )
            row[ADAPTER_RUNTIME_ADAPTER_ISOLATION_KEY_FIELD] = str(
                manifest.get(_ADAPTER_RUNTIME_ADAPTER_ISOLATION_MANIFEST_KEY, "")
            )
            row[ADAPTER_RUNTIME_SWITCH_MODE_FIELD] = str(
                manifest.get(_ADAPTER_RUNTIME_SWITCH_MODE_MANIFEST_KEY, "")
            )
            row[ADAPTER_RUNTIME_SHARING_POLICY_FIELD] = str(
                manifest.get(_ADAPTER_RUNTIME_SHARING_POLICY_MANIFEST_KEY, "")
            )
            row[ADAPTER_RUNTIME_COMPATIBILITY_STATUS_FIELD] = str(
                manifest.get(_ADAPTER_RUNTIME_COMPATIBILITY_STATUS_MANIFEST_KEY, "")
            )

    @classmethod
    def _job_manifest(cls, job: ModelOpsJob) -> dict[str, Any]:
        if job.operation == "registry_snapshot":
            return {}
        if job.manifest_cached:
            return job.manifest
        if not job.manifest_json:
            return {}
        return cls._decode_manifest_json(job.manifest_json)

    @classmethod
    def _removed_derived_targets_from_ordered_jobs(
        cls,
        jobs: tuple[ModelOpsJob, ...],
    ) -> dict[str, set[str]]:
        removed_model_ids: set[str] = set()
        removed_manifest_paths: set[str] = set()
        removed_adapter_manifest_paths: set[str] = set()
        removed_activation_job_ids: set[str] = set()
        for job in jobs:
            if job.operation != "remove_derived_model" or job.status != "completed":
                continue
            manifest = cls._job_manifest(job)
            derived_model_id = str(manifest.get("derived_model_id", "")).strip()
            if derived_model_id:
                removed_model_ids.add(derived_model_id)
            activation_manifest_path = str(manifest.get("activation_manifest_path", "")).strip()
            if activation_manifest_path:
                removed_manifest_paths.add(activation_manifest_path)
            adapter_manifest_path = str(manifest.get("adapter_manifest_path", "")).strip()
            if adapter_manifest_path:
                removed_adapter_manifest_paths.add(adapter_manifest_path)
            activation_job_id = str(manifest.get("activation_job_id", "")).strip()
            if activation_job_id:
                removed_activation_job_ids.add(activation_job_id)
        return {
            "model_ids": removed_model_ids,
            "manifest_paths": removed_manifest_paths,
            "adapter_manifest_paths": removed_adapter_manifest_paths,
            "activation_job_ids": removed_activation_job_ids,
        }

    @classmethod
    def _active_derived_model_job_rows(
        cls,
        jobs: tuple[ModelOpsJob, ...],
    ) -> tuple[tuple[ModelOpsJob, dict[str, Any], str], ...]:
        removed_targets = cls._removed_derived_targets_from_ordered_jobs(jobs)
        removed_model_ids = removed_targets["model_ids"]
        removed_manifest_paths = removed_targets["manifest_paths"]
        removed_activation_job_ids = removed_targets["activation_job_ids"]
        active_rows: list[tuple[ModelOpsJob, dict[str, Any], str]] = []
        for job in jobs:
            if job.operation != "activate_adapter" or job.status != "completed":
                continue
            if job.job_id in removed_activation_job_ids:
                continue
            activation_manifest_path = str(job.output_path).strip()
            manifest = cls._job_manifest(job)
            candidate_model_id = str(manifest.get("derived_model_id", "")).strip()
            if candidate_model_id in removed_model_ids or activation_manifest_path in removed_manifest_paths:
                continue
            active_rows.append((job, manifest, activation_manifest_path))
        return tuple(active_rows)

    def resolve_derived_model_target(
        self,
        *,
        derived_model_id: str = "",
        manifest_path: str = "",
    ) -> dict[str, Any] | None:
        if derived_model_id and not manifest_path:
            lookup = self._cached_active_derived_model_by_id().get(derived_model_id)
            if lookup is not None:
                resolved_activation_manifest_path = lookup.resolved_activation_manifest_path
                if resolved_activation_manifest_path is None:
                    resolved_activation_manifest_path = str(
                        Path(lookup.activation_manifest_path).expanduser().resolve()
                    )
                    lookup.resolved_activation_manifest_path = resolved_activation_manifest_path
                return self._cached_derived_model_target_payload(
                    lookup,
                    resolved_activation_manifest_path=resolved_activation_manifest_path,
                )
            normalized_model_id = derived_model_id.strip()
            if not normalized_model_id or normalized_model_id == derived_model_id:
                return None
            lookup = self._cached_active_derived_model_by_id().get(normalized_model_id)
            if lookup is None:
                return None
            resolved_activation_manifest_path = lookup.resolved_activation_manifest_path
            if resolved_activation_manifest_path is None:
                resolved_activation_manifest_path = str(
                    Path(lookup.activation_manifest_path).expanduser().resolve()
                )
                lookup.resolved_activation_manifest_path = resolved_activation_manifest_path
            return self._cached_derived_model_target_payload(
                lookup,
                resolved_activation_manifest_path=resolved_activation_manifest_path,
            )

        normalized_model_id = derived_model_id.strip()
        normalized_manifest_path = ""
        raw_manifest_path = manifest_path.strip()
        if raw_manifest_path:
            cached_by_manifest_path = self._cached_active_derived_model_by_manifest_path()
            if raw_manifest_path in cached_by_manifest_path:
                normalized_manifest_path = raw_manifest_path
            else:
                normalized_manifest_path = str(Path(raw_manifest_path).expanduser().resolve())
        if not normalized_model_id and not normalized_manifest_path:
            return None

        if normalized_model_id:
            lookup = self._cached_active_derived_model_by_id().get(normalized_model_id)
            if lookup is None:
                return None
            resolved_activation_manifest_path = lookup.resolved_activation_manifest_path
            if resolved_activation_manifest_path is None:
                resolved_activation_manifest_path = str(
                    Path(lookup.activation_manifest_path).expanduser().resolve()
                )
                lookup.resolved_activation_manifest_path = resolved_activation_manifest_path
            if normalized_manifest_path and resolved_activation_manifest_path != normalized_manifest_path:
                return None
            return self._cached_derived_model_target_payload(
                lookup,
                resolved_activation_manifest_path=resolved_activation_manifest_path,
            )

        lookup = cached_by_manifest_path.get(normalized_manifest_path)
        if lookup is None:
            return None
        return self._cached_derived_model_target_payload(
            lookup,
            resolved_activation_manifest_path=normalized_manifest_path,
        )

    def active_derived_model_manifests(self) -> tuple[dict[str, Any], ...]:
        cached_manifests = self._active_derived_model_manifests_cache
        if cached_manifests is None:
            cached_manifests = tuple(
                manifest for _, manifest, _ in self._cached_active_derived_model_job_rows()
            )
            self._active_derived_model_manifests_cache = cached_manifests
        return cached_manifests

    def _max_numeric_job_id(self) -> int:
        max_job_id = 0
        for job_id in self._jobs:
            try:
                max_job_id = max(max_job_id, int(job_id.rsplit("-", maxsplit=1)[-1]))
            except ValueError:
                continue
        return max_job_id

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if isinstance(value, dict):
            updated: dict[Any, Any] | None = None
            for key, item in value.items():
                safe_item = cls._json_safe(item)
                if updated is not None:
                    updated[key] = safe_item
                elif safe_item is not item:
                    updated = dict(value)
                    updated[key] = safe_item
            return value if updated is None else updated
        if isinstance(value, list):
            updated_list: list[Any] | None = None
            for index, item in enumerate(value):
                safe_item = cls._json_safe(item)
                if updated_list is not None:
                    updated_list.append(safe_item)
                elif safe_item is not item:
                    updated_list = value[:index]
                    updated_list.append(safe_item)
            return value if updated_list is None else updated_list
        if isinstance(value, float) and math.isfinite(value) is False:
            return None
        return value

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
        if job.operation != "registry_snapshot":
            if job.manifest_cached:
                manifest = job.manifest
            elif job.manifest_json:
                manifest = ModelOpsJobRegistry._decode_manifest_json(job.manifest_json)

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
        removed_targets = ModelOpsJobRegistry._removed_derived_targets(jobs)
        removed_model_ids = removed_targets["model_ids"]
        removed_adapter_manifest_paths = removed_targets["adapter_manifest_paths"]
        removed_activation_job_ids = removed_targets["activation_job_ids"]

        for job in jobs:
            if job["operation"] != "upload" or job["status"] != "completed":
                continue
            manifest = job.get("manifest") or {}
            ext = manifest.get("ext") if isinstance(manifest.get("ext"), dict) else {}
            artifact_kind = str(ext.get("artifact_kind", manifest.get("artifact_kind", "")))
            if artifact_kind != "adapter":
                continue

            raw_lineage = manifest.get("parent_lineage")
            publish = {
                "job_id": job["job_id"],
                "target_repo": str(manifest.get("published_repo", manifest.get("target_repo", ext.get("target_repo", "")))),
                "publish_backend": str(manifest.get("upload_backend", manifest.get("publish_backend", ""))),
                "export_artifact_kind": str(manifest.get("export_artifact_kind", "")),
                "parent_lineage": raw_lineage if isinstance(raw_lineage, dict) else {},
            }
            adapter_name = str(ext.get("adapter_name", manifest.get("adapter_name", "")))
            artifact_path = str(ext.get("artifact_path", manifest.get("artifact_path", "")))
            if adapter_name:
                publish_by_name.setdefault(adapter_name, publish)
            if artifact_path:
                publish_by_path.setdefault(artifact_path, publish)

        for job in jobs:
            if job["operation"] != "activate_adapter" or job["status"] != "completed":
                continue
            if job["job_id"] in removed_activation_job_ids:
                continue
            manifest = job.get("manifest") or {}
            activation = {
                "job_id": job["job_id"],
                "derived_model_id": str(manifest.get("derived_model_id", "")),
                "derived_model_path": str(manifest.get("derived_model_path", "")),
                "derived_model_alias": str(manifest.get("derived_model_alias", "")),
                "activation_mode": str(manifest.get("activation_mode", "")),
                "runtime_mode": _runtime_mode_from_activation(str(manifest.get("activation_mode", ""))),
                "activation_backend": str(manifest.get("activation_backend", "")),
                "activation_duration_ms": float(manifest.get("activation_duration_ms", 0.0)),
                "adapter_manifest_path": str(manifest.get("adapter_manifest_path", "")),
                "adapter_weights_path": str(manifest.get("adapter_weights_path", "")),
                "adapter_scope": str(manifest.get("adapter_scope", "")),
                "training_surface": str(manifest.get("training_surface", "")),
                "component_model_type": str(manifest.get("component_model_type", "")),
                "component_family": str(manifest.get("component_family", "")),
                "component_model_path": str(manifest.get("component_model_path", "")),
                "activation_manifest_path": str(job.get("output_path", "")),
                "source_adapter_job_id": str(manifest.get("source_adapter_job_id", "")),
                "status": "activated",
            }
            ModelOpsJobRegistry._copy_adapter_runtime_row_fields(activation, manifest)
            if activation["derived_model_id"] in removed_model_ids:
                continue
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
            removal_applied = output_path in removed_adapter_manifest_paths
            adapter_scope = str(manifest.get("adapter_scope", ""))
            training_surface = str(manifest.get("training_surface", ""))
            component_model_type = str(manifest.get("component_model_type", ""))
            component_family = str(manifest.get("component_family", ""))
            component_model_path = str(manifest.get("component_model_path", ""))

            if publish:
                status = "published"
            elif removal_applied:
                status = job["status"]
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
                    "experiment_group_id": str(manifest.get("experiment_group_id", "")),
                    "experiment_group_title": str(manifest.get("experiment_group_title", "")),
                    "preset_id": str(manifest.get("preset_id", "")),
                    "preset_title": str(manifest.get("preset_title", "")),
                    "output_path": output_path,
                    "adapter_set_hash": adapter_set_hash,
                    "target_repo": str(manifest.get("target_repo", "")),
                    "published_repo": publish["target_repo"] if publish else "",
                    "publish_job_id": publish["job_id"] if publish else "",
                    "publish_backend": publish["publish_backend"] if publish else "",
                    "publish_artifact_kind": publish["export_artifact_kind"] if publish else "",
                    "publish_parent_lineage": publish["parent_lineage"] if publish else {},
                    "status": status,
                    "activation_status": "removed" if removal_applied else activation["status"] if activation else "pending_activation",
                    "derived_model_id": "" if removal_applied else activation["derived_model_id"] if activation else "",
                    "derived_model_path": "" if removal_applied else activation["derived_model_path"] if activation else "",
                    "derived_model_alias": "" if removal_applied else activation["derived_model_alias"] if activation else "",
                    "activation_job_id": "" if removal_applied else activation["job_id"] if activation else "",
                    "activation_mode": "" if removal_applied else activation["activation_mode"] if activation else "",
                    "runtime_mode": 0 if removal_applied else (activation.get("runtime_mode", 0) if activation else 0),
                    "activation_backend": "" if removal_applied else activation["activation_backend"] if activation else "",
                    "adapter_manifest_path": activation["adapter_manifest_path"] if activation else output_path,
                    "adapter_weights_path": "" if removal_applied else activation["adapter_weights_path"] if activation else "",
                    "adapter_scope": (
                        "" if removal_applied else activation["adapter_scope"] if activation else adapter_scope
                    ),
                    "training_surface": (
                        ""
                        if removal_applied
                        else activation["training_surface"] if activation else training_surface
                    ),
                    "component_model_type": (
                        ""
                        if removal_applied
                        else activation["component_model_type"] if activation else component_model_type
                    ),
                    "component_family": (
                        ""
                        if removal_applied
                        else activation["component_family"] if activation else component_family
                    ),
                    "component_model_path": (
                        ""
                        if removal_applied
                        else activation["component_model_path"] if activation else component_model_path
                    ),
                    ADAPTER_RUNTIME_BASE_REUSE_KEY_FIELD: (
                        ""
                        if removal_applied
                        else activation.get(ADAPTER_RUNTIME_BASE_REUSE_KEY_FIELD, "") if activation else ""
                    ),
                    ADAPTER_RUNTIME_ADAPTER_ISOLATION_KEY_FIELD: (
                        ""
                        if removal_applied
                        else activation.get(ADAPTER_RUNTIME_ADAPTER_ISOLATION_KEY_FIELD, "") if activation else ""
                    ),
                    ADAPTER_RUNTIME_SWITCH_MODE_FIELD: (
                        "" if removal_applied else activation.get(ADAPTER_RUNTIME_SWITCH_MODE_FIELD, "") if activation else ""
                    ),
                    ADAPTER_RUNTIME_SHARING_POLICY_FIELD: (
                        "" if removal_applied else activation.get(ADAPTER_RUNTIME_SHARING_POLICY_FIELD, "") if activation else ""
                    ),
                    ADAPTER_RUNTIME_COMPATIBILITY_STATUS_FIELD: (
                        ""
                        if removal_applied
                        else activation.get(ADAPTER_RUNTIME_COMPATIBILITY_STATUS_FIELD, "") if activation else ""
                    ),
                    "source_adapter_job_id": activation["source_adapter_job_id"] if activation else job["job_id"],
                    "activation_duration_ms": 0.0 if removal_applied else activation["activation_duration_ms"] if activation else 0.0,
                    "exportable_state": "ready",
                    "published_state": "published" if publish else "not_published",
                    "response_only": bool(manifest.get("response_only", False)),
                    "gradient_checkpointing": bool(manifest.get("gradient_checkpointing", False)),
                    "training_duration_ms": float(manifest.get("training_duration_ms", 0.0)),
                    "checkpoint_count": int(
                        manifest.get(
                            "checkpoint_count",
                            manifest.get("experiment.checkpoint_count", 0),
                        )
                    ),
                    "latest_checkpoint_path": str(
                        manifest.get(
                            "latest_checkpoint_path",
                            manifest.get("experiment.latest_checkpoint_path", ""),
                        )
                    ),
                    "resume_source_path": str(
                        manifest.get(
                            "resume_source_path",
                            manifest.get("experiment.resume_source_path", ""),
                        )
                    ),
                    "resume_source_job_id": str(manifest.get("resume_source_job_id", "")),
                    "resume_source_manifest_path": str(manifest.get("resume_source_manifest_path", "")),
                    "resume_ready": bool(
                        manifest.get(
                            "resume_ready",
                            manifest.get("experiment.resume_ready", False),
                        )
                    ),
                    "tokens_per_second": float(
                        manifest.get(
                            "tokens_per_second",
                            manifest.get("training.tokens_per_second", 0.0),
                        )
                    ),
                    "peak_memory_gb": float(
                        manifest.get(
                            "peak_memory_gb",
                            manifest.get("training.peak_memory_gb", 0.0),
                        )
                    ),
                    "adapter_publish_ms": float(manifest.get("adapter_publish_ms", 0.0)),
                }
            )

        return adapters

    @staticmethod
    def _derived_model_registry(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        publish_by_model_path: dict[str, dict[str, Any]] = {}
        publish_by_manifest_path: dict[str, dict[str, Any]] = {}
        for job in jobs:
            if job["operation"] != "upload" or job["status"] != "completed":
                continue
            manifest = job.get("manifest") or {}
            export_artifact_kind = str(manifest.get("export_artifact_kind", ""))
            if export_artifact_kind != "merged_export":
                continue
            raw_lineage = manifest.get("parent_lineage")
            raw_processor_config_files = manifest.get("processor_config_files")
            publish = {
                "job_id": job["job_id"],
                "target_repo": str(manifest.get("published_repo", manifest.get("target_repo", ""))),
                "publish_backend": str(manifest.get("upload_backend", manifest.get("publish_backend", ""))),
                "export_artifact_kind": export_artifact_kind,
                "distribution_contract": str(manifest.get("distribution_contract") or ""),
                "processor_config_files": (
                    list(raw_processor_config_files)
                    if isinstance(raw_processor_config_files, list)
                    else []
                ),
                "parent_lineage": raw_lineage if isinstance(raw_lineage, dict) else {},
            }
            parent_lineage = publish["parent_lineage"]
            manifest_path = str(parent_lineage.get("local_manifest_path", "")).strip()
            model_path = str(parent_lineage.get("local_artifact_path", "")).strip()
            if manifest_path:
                publish_by_manifest_path.setdefault(manifest_path, publish)
            if model_path:
                publish_by_model_path.setdefault(model_path, publish)

        removed_targets = ModelOpsJobRegistry._removed_derived_targets(jobs)
        removed_model_ids = removed_targets["model_ids"]
        removed_activation_job_ids = removed_targets["activation_job_ids"]
        derived_models: list[dict[str, Any]] = []
        for job in jobs:
            if job["operation"] != "activate_adapter" or job["status"] != "completed":
                continue
            if job["job_id"] in removed_activation_job_ids:
                continue
            manifest = job.get("manifest") or {}
            derived_model_id = str(manifest.get("derived_model_id", ""))
            if derived_model_id in removed_model_ids:
                continue
            activation_manifest_path = str(job.get("output_path", "")).strip()
            model_path = str(manifest.get("derived_model_path", "")).strip()
            publish = (
                (activation_manifest_path and publish_by_manifest_path.get(activation_manifest_path))
                or (model_path and publish_by_model_path.get(model_path))
            )
            derived_model = {
                "job_id": job["job_id"],
                "model_id": derived_model_id,
                "model_path": model_path,
                "adapter_set_hash": str(manifest.get("adapter_set_hash", "")),
                "adapter_manifest_path": str(manifest.get("adapter_manifest_path", "")),
                "adapter_weights_path": str(manifest.get("adapter_weights_path", "")),
                "adapter_name": str(manifest.get("adapter_name", "")),
                "adapter_scope": str(manifest.get("adapter_scope", "")),
                "training_surface": str(manifest.get("training_surface", "")),
                "component_model_type": str(manifest.get("component_model_type", "")),
                "component_family": str(manifest.get("component_family", "")),
                "component_model_path": str(manifest.get("component_model_path", "")),
                "derived_model_alias": str(manifest.get("derived_model_alias", "")),
                "source_adapter_job_id": str(manifest.get("source_adapter_job_id", "")),
                "source_model": str(manifest.get("source_model", "")),
                "activation_mode": str(manifest.get("activation_mode", "")),
                "runtime_mode": _runtime_mode_from_activation(str(manifest.get("activation_mode", ""))),
                "activation_backend": str(manifest.get("activation_backend", "")),
                "activation_manifest_path": activation_manifest_path,
                "published_repo": publish["target_repo"] if publish else "",
                "publish_job_id": publish["job_id"] if publish else "",
                "publish_backend": publish["publish_backend"] if publish else "",
                "publish_artifact_kind": publish["export_artifact_kind"] if publish else "",
                "publish_parent_lineage": publish["parent_lineage"] if publish else {},
                "distribution_contract": publish["distribution_contract"] if publish else "",
                "processor_config_files": publish["processor_config_files"] if publish else [],
                "published_state": "published" if publish else "not_published",
                "status": "activated",
            }
            ModelOpsJobRegistry._copy_adapter_runtime_row_fields(derived_model, manifest)
            derived_models.append(derived_model)
        return derived_models

    @staticmethod
    def _removed_derived_targets(jobs: list[dict[str, Any]]) -> dict[str, set[str]]:
        removed_model_ids: set[str] = set()
        removed_manifest_paths: set[str] = set()
        removed_adapter_manifest_paths: set[str] = set()
        removed_activation_job_ids: set[str] = set()

        for job in jobs:
            if job["operation"] != "remove_derived_model" or job["status"] != "completed":
                continue
            manifest = job.get("manifest") or {}
            derived_model_id = str(manifest.get("derived_model_id", "")).strip()
            if derived_model_id:
                removed_model_ids.add(derived_model_id)
            activation_manifest_path = str(manifest.get("activation_manifest_path", "")).strip()
            if activation_manifest_path:
                removed_manifest_paths.add(activation_manifest_path)
            adapter_manifest_path = str(manifest.get("adapter_manifest_path", "")).strip()
            if adapter_manifest_path:
                removed_adapter_manifest_paths.add(adapter_manifest_path)
            activation_job_id = str(manifest.get("activation_job_id", "")).strip()
            if activation_job_id:
                removed_activation_job_ids.add(activation_job_id)

        return {
            "model_ids": removed_model_ids,
            "manifest_paths": removed_manifest_paths,
            "adapter_manifest_paths": removed_adapter_manifest_paths,
            "activation_job_ids": removed_activation_job_ids,
        }

    @staticmethod
    def _publish_registry(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        publishes: list[dict[str, Any]] = []
        for job in jobs:
            if job["operation"] != "upload" or job["status"] != "completed":
                continue

            manifest = job.get("manifest") or {}
            ext = manifest.get("ext") if isinstance(manifest.get("ext"), dict) else {}
            # `or ""` guards against the key being present with a JSON `null`
            # value — `str(None)` would otherwise corrupt the field to "None"
            # and bypass the empty-string gate below.
            export_artifact_kind = str(manifest.get("export_artifact_kind") or "").strip()
            source_artifact_kind = str(
                manifest.get("source_artifact_kind") or ext.get("artifact_kind") or ""
            ).strip()
            target_repo = str(
                manifest.get("published_repo")
                or manifest.get("target_repo")
                or ext.get("target_repo")
                or ""
            )
            published_url = str(manifest.get("published_url") or "")
            # The export-kind / source-artifact-kind branches admit Module-5+
            # upload manifests. Pre-Module-5 worker emissions only carried
            # `published_repo` + `upload_backend` without an explicit kind, so
            # the third branch admits any completed upload that successfully
            # reached a remote target (non-empty target_repo or published_url).
            # Together this covers legacy uploads while keeping unrelated
            # `upload` jobs (no remote target, no recognized kind) out of the
            # publishes lineage view.
            if (
                export_artifact_kind == ""
                and source_artifact_kind
                not in {
                    "adapter",
                    "derived_text_model",
                    "converted_model_bundle",
                    "quantized_model_bundle",
                }
                and not target_repo
                and not published_url
            ):
                continue

            raw_lineage = manifest.get("parent_lineage")
            parent_lineage = raw_lineage if isinstance(raw_lineage, dict) else {}
            raw_published_files = manifest.get("published_files")
            published_files = (
                list(raw_published_files) if isinstance(raw_published_files, list) else []
            )
            raw_processor_config_files = manifest.get("processor_config_files")
            processor_config_files = (
                list(raw_processor_config_files)
                if isinstance(raw_processor_config_files, list)
                else []
            )
            publishes.append(
                {
                    "job_id": job["job_id"],
                    "status": "published",
                    "target_repo": target_repo,
                    "published_url": published_url,
                    "published_ref": str(manifest.get("published_ref") or ""),
                    "published_files": published_files,
                    "processor_config_files": processor_config_files,
                    "publish_backend": str(
                        manifest.get("upload_backend")
                        or manifest.get("publish_backend")
                        or ""
                    ),
                    "export_artifact_kind": export_artifact_kind,
                    "source_artifact_kind": source_artifact_kind,
                    "distribution_contract": str(manifest.get("distribution_contract") or ""),
                    "source_job_id": str(parent_lineage.get("source_job_id") or ""),
                    "source_artifact_path": str(
                        parent_lineage.get("local_artifact_path")
                        or manifest.get("artifact_path")
                        or ""
                    ),
                    "source_manifest_path": str(
                        parent_lineage.get("local_manifest_path")
                        or manifest.get("source_manifest_path")
                        or ""
                    ),
                    "source_model": str(
                        manifest.get("source_model_from_artifact")
                        or manifest.get("source_model")
                        or job["source_model"]
                        or ""
                    ),
                    "adapter_name": str(
                        manifest.get("adapter_name") or ext.get("adapter_name") or ""
                    ),
                    "derived_model_id": str(
                        parent_lineage.get("derived_model_id")
                        or manifest.get("derived_model_id")
                        or ""
                    ),
                    "activation_mode": str(
                        parent_lineage.get("activation_mode")
                        or manifest.get("activation_mode")
                        or ""
                    ),
                    "parent_lineage": parent_lineage,
                    "receipt_path": str(job.get("output_path") or ""),
                    "upload_duration_ms": float(manifest.get("upload_duration_ms") or 0.0),
                }
            )
        return publishes

    @staticmethod
    def _download_registry(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        downloads: list[dict[str, Any]] = []
        for job in jobs:
            if job["operation"] != "download":
                continue

            manifest = job.get("manifest") or {}
            downloaded_bytes = int(manifest.get("downloaded_bytes", 0))
            total_bytes = int(manifest.get("total_bytes", 0))
            partial_path = str(manifest.get("partial_path", ""))
            status = str(manifest.get("terminal_state", manifest.get("status", job["status"])))
            downloads.append(
                {
                    "job_id": job["job_id"],
                    "source_model": job["source_model"],
                    "status": status,
                    "stage": str(manifest.get("stage", job["stage"])),
                    "pct": float(manifest.get("pct", job["pct"])),
                    "output_dir": str(manifest.get("output_dir", job["output_dir"])),
                    "output_path": str(manifest.get("output_path", job["output_path"])),
                    "partial_path": partial_path,
                    "state_path": str(manifest.get("state_path", "")),
                    "selected_mirror": str(manifest.get("selected_mirror", "")),
                    "downloaded_bytes": downloaded_bytes,
                    "total_bytes": total_bytes,
                    "resume_used": bool(manifest.get("resume_used", False)),
                    "resume_from_bytes": int(manifest.get("resume_from_bytes", 0)),
                    "retry_count": int(manifest.get("retry_count", 0)),
                    "stall_detection_count": int(manifest.get("stall_detection_count", 0)),
                    "stall_reason": str(manifest.get("stall_reason", "")),
                    "resume_ready": (
                        partial_path != ""
                        and downloaded_bytes > 0
                        and (total_bytes == 0 or downloaded_bytes < total_bytes)
                        and status in {"failed", "stalled", "running", "retrying"}
                    ),
                }
            )
        return downloads

    def _experiment_groups(self) -> list[dict[str, Any]]:
        if self._jobs_root is None:
            return []
        index_payload = self._lora_experiment_store.load_index(self._jobs_root)
        groups = index_payload.get("groups", [])
        return groups if isinstance(groups, list) else []
