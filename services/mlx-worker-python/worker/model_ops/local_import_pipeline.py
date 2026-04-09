from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from packages.protocol.python.worker.v1 import maintenance_pb2

from worker.model_ops.download_pipeline import DownloadPipeline, DownloadPipelineResult, DownloadSnapshot
from worker.model_ops.errors import ModelOperationError


class LocalImportPipeline:
    def run(
        self,
        request: maintenance_pb2.ConvertModelRequest,
        *,
        job_id: str,
        output_dir: Path,
    ) -> DownloadPipelineResult:
        ext = dict(request.ext)
        source_dir = self._resolve_source_dir(ext)
        managed_root = self._resolve_managed_root(ext)
        model_id = ext.get("melix.import_model_id", "").strip() or request.source_model.strip()
        if not model_id:
            raise ModelOperationError(
                code="invalid_argument",
                message="local import requires a non-empty model identifier.",
            )
        model_kind = ext.get("melix.model_kind", "").strip() or "text"
        revision = ext.get("melix.revision", "").strip() or "main"
        materialized_dir = managed_root / "local" / model_id / revision
        materialized_dir.parent.mkdir(parents=True, exist_ok=True)
        if materialized_dir.exists():
            shutil.rmtree(materialized_dir)
        shutil.copytree(source_dir, materialized_dir)

        registry_manifest = self._registry_manifest_payload(
            model_id=model_id,
            model_kind=model_kind,
            revision=revision,
            source_dir=source_dir,
            materialized_dir=materialized_dir,
        )
        manifest_path = materialized_dir / "manifest.json"
        manifest_path.write_text(json.dumps(registry_manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")

        state_path = output_dir / "local_import.state.json"
        state_payload = self._state_payload(
            request=request,
            job_id=job_id,
            output_dir=output_dir,
            state_path=state_path,
            source_dir=source_dir,
            materialized_dir=materialized_dir,
            model_id=model_id,
            revision=revision,
            ext=ext,
        )
        DownloadPipeline._write_json_atomically(state_path, state_payload)
        manifest_json = json.dumps(state_payload, sort_keys=True)
        return DownloadPipelineResult(
            output_path=materialized_dir,
            snapshots=[
                DownloadSnapshot(stage="prepare", pct=0.0, manifest_json=manifest_json),
                DownloadSnapshot(stage="materialize", pct=1.0, manifest_json=manifest_json),
            ],
        )

    @staticmethod
    def _resolve_source_dir(ext: dict[str, str]) -> Path:
        source_path_raw = ext.get("source_path", "").strip()
        if not source_path_raw:
            raise ModelOperationError(
                code="invalid_argument",
                message="local import requires ext.source_path.",
            )
        source_dir = Path(source_path_raw).expanduser().resolve()
        if not source_dir.is_dir():
            raise ModelOperationError(
                code="invalid_argument",
                message="local import requires an existing source directory.",
            )
        return source_dir

    @staticmethod
    def _resolve_managed_root(ext: dict[str, str]) -> Path:
        managed_root = ext.get("melix.managed_root", "").strip() or os.environ.get("MELIX_MANAGED_MODEL_ROOT", "").strip()
        if not managed_root:
            raise ModelOperationError(
                code="invalid_argument",
                message="local import requires MELIX_MANAGED_MODEL_ROOT.",
            )
        return Path(managed_root).expanduser().resolve()

    @staticmethod
    def _registry_manifest_payload(
        *,
        model_id: str,
        model_kind: str,
        revision: str,
        source_dir: Path,
        materialized_dir: Path,
    ) -> dict[str, object]:
        return {
            "schema_version": "melix.model_registry_manifest.v1",
            "model_id": model_id,
            "model_kind": model_kind,
            "revision": revision,
            "provider_id": "local",
            "organization_id": "local",
            "model_name": model_id,
            "variant_id": revision,
            "ext": {
                "melix.registry_provider_id": "local",
                "melix.source_kind": "local_path",
                "melix.source_locator": str(source_dir),
                "melix.model_path": str(materialized_dir),
            },
        }

    @staticmethod
    def _state_payload(
        *,
        request: maintenance_pb2.ConvertModelRequest,
        job_id: str,
        output_dir: Path,
        state_path: Path,
        source_dir: Path,
        materialized_dir: Path,
        model_id: str,
        revision: str,
        ext: dict[str, str],
    ) -> dict[str, object]:
        merged_ext = dict(ext)
        merged_ext["melix.source_kind"] = "local_path"
        merged_ext["melix.source_locator"] = str(source_dir)
        merged_ext["melix.revision"] = revision
        return {
            "schema_version": "melix.local_import_job.v1",
            "job_id": job_id,
            "operation": "local_import",
            "model_id": model_id,
            "managed_model_path": str(materialized_dir),
            "source_model": request.source_model,
            "output_dir": str(output_dir),
            "status": "completed",
            "terminal_state": "completed",
            "stage": "materialize",
            "pct": 1.0,
            "source_path": str(source_dir),
            "output_path": str(materialized_dir),
            "state_path": str(state_path),
            "ext": merged_ext,
            "metrics": {
                "local_import.copy_success": 1.0,
            },
        }
