from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any

from packages.protocol.python.worker.v1 import maintenance_pb2

from worker.model_ops.errors import ModelOperationError

_UPLOAD_RECEIPT_SCHEMA_VERSION = "melix.upload_receipt.v1"


@dataclass(frozen=True)
class UploadReceiptPipelineResult:
    receipt_path: Path
    manifest_payload: dict[str, Any]
    artifact_bytes: int
    manifest_bytes: int
    runtime: str


@dataclass(frozen=True)
class SourceArtifactDescriptor:
    artifact_path: str
    artifact_kind: str
    schema_version: str
    manifest_path: str
    source_model: str
    manifest_payload: dict[str, Any] | None


class UploadReceiptPipeline:
    def run(
        self,
        request: maintenance_pb2.ConvertModelRequest,
        *,
        job_id: str,
        output_dir: Path,
    ) -> UploadReceiptPipelineResult:
        started_at = time.perf_counter()
        descriptor = self._resolve_source_artifact(request)
        receipt_path = (output_dir / job_id / "upload.receipt.json").resolve()
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        runtime = ""
        source_manifest = descriptor.manifest_payload or {}
        compatibility = source_manifest.get("compatibility")
        if isinstance(compatibility, dict):
            runtime = str(compatibility.get("runtime", "")).strip()

        manifest_payload = {
            "schema_version": _UPLOAD_RECEIPT_SCHEMA_VERSION,
            "artifact_kind": "upload_receipt",
            "job_id": job_id,
            "operation": "upload",
            "status": "recorded",
            "source_model": request.source_model,
            "target_repo": request.ext.get("target_repo", ""),
            "artifact_path": descriptor.artifact_path,
            "source_artifact_kind": descriptor.artifact_kind,
            "source_artifact_schema_version": descriptor.schema_version,
            "source_manifest_path": descriptor.manifest_path,
            "source_model_from_artifact": descriptor.source_model,
            "upload_backend": "melix_local_receipt",
            "upload_duration_ms": (time.perf_counter() - started_at) * 1000.0,
            "ext": dict(request.ext),
        }
        if runtime:
            manifest_payload["runtime"] = runtime
        if descriptor.manifest_payload is not None:
            linked_quantization = self._linked_quantization(source_manifest)
            if linked_quantization is not None:
                manifest_payload["linked_quantization"] = linked_quantization
            if descriptor.artifact_kind == "adapter":
                manifest_payload["adapter_name"] = str(source_manifest.get("adapter_name", ""))
                manifest_payload["source_adapter_job_id"] = str(source_manifest.get("job_id", ""))
            if descriptor.artifact_kind == "converted_model_bundle":
                manifest_payload["target_format"] = str(source_manifest.get("target_format", ""))
                manifest_payload["conversion_backend"] = str(source_manifest.get("conversion_backend", ""))

        manifest_bytes = 0
        artifact_bytes = 0
        while True:
            manifest_payload["manifest_path"] = str(receipt_path)
            manifest_payload["bundle_path"] = str(receipt_path)
            manifest_payload["manifest_bytes"] = manifest_bytes
            manifest_payload["artifact_bytes"] = artifact_bytes
            next_manifest_bytes = self._write_manifest(receipt_path, manifest_payload)
            next_artifact_bytes = next_manifest_bytes
            if next_manifest_bytes == manifest_bytes and next_artifact_bytes == artifact_bytes:
                break
            manifest_bytes = next_manifest_bytes
            artifact_bytes = next_artifact_bytes

        return UploadReceiptPipelineResult(
            receipt_path=receipt_path,
            manifest_payload=manifest_payload,
            artifact_bytes=artifact_bytes,
            manifest_bytes=manifest_bytes,
            runtime=runtime,
        )

    def _resolve_source_artifact(
        self,
        request: maintenance_pb2.ConvertModelRequest,
    ) -> SourceArtifactDescriptor:
        explicit_path = request.ext.get("artifact_path", "").strip()
        requested_kind = request.ext.get("artifact_kind", "").strip()
        if not explicit_path:
            return SourceArtifactDescriptor(
                artifact_path=request.source_model,
                artifact_kind=requested_kind or "model",
                schema_version="",
                manifest_path=request.ext.get("artifact_manifest_path", "").strip(),
                source_model="",
                manifest_payload=None,
            )

        artifact_path = Path(explicit_path).expanduser().resolve()
        if not artifact_path.exists():
            raise ModelOperationError(
                code="invalid_artifact",
                message="upload requires a valid artifact_path when an explicit path is provided.",
            )

        manifest_path = artifact_path / "manifest.json" if artifact_path.is_dir() else artifact_path
        manifest_payload: dict[str, Any] | None = None
        if manifest_path.is_file():
            try:
                loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ModelOperationError(
                    code="invalid_artifact",
                    message="Artifact manifest is not valid JSON.",
                ) from exc
            if isinstance(loaded, dict):
                manifest_payload = loaded

        if manifest_payload is None:
            return SourceArtifactDescriptor(
                artifact_path=str(artifact_path),
                artifact_kind=requested_kind or "model",
                schema_version="",
                manifest_path=str(manifest_path) if manifest_path.is_file() else "",
                source_model="",
                manifest_payload=None,
            )

        return SourceArtifactDescriptor(
            artifact_path=str(artifact_path),
            artifact_kind=str(manifest_payload.get("artifact_kind", "")).strip() or requested_kind or "model",
            schema_version=str(manifest_payload.get("schema_version", "")).strip(),
            manifest_path=str(manifest_path),
            source_model=str(manifest_payload.get("source_model", "")).strip(),
            manifest_payload=manifest_payload,
        )

    @staticmethod
    def _linked_quantization(manifest_payload: dict[str, Any]) -> dict[str, Any] | None:
        if str(manifest_payload.get("artifact_kind", "")).strip() != "quantized_model_bundle":
            return None
        calibration = manifest_payload.get("calibration")
        compatibility = manifest_payload.get("compatibility")
        quant_profile = manifest_payload.get("quant_profile")
        if not isinstance(calibration, dict):
            calibration = {}
        if not isinstance(compatibility, dict):
            compatibility = {}
        if not isinstance(quant_profile, dict):
            quant_profile = {}
        return {
            "artifact_kind": "quantized_model_bundle",
            "artifact_path": str(manifest_payload.get("artifact_path", "")),
            "manifest_path": str(manifest_payload.get("manifest_path", "")),
            "source_model": str(manifest_payload.get("source_model", "")),
            "quant_profile_id": str(quant_profile.get("quant_profile_id", "")),
            "calibration_sample_count": int(calibration.get("sample_count", 0) or 0),
            "smoke_test_passed": bool(compatibility.get("smoke_test_passed", False)),
        }

    @staticmethod
    def _write_manifest(path: Path, payload: dict[str, Any]) -> int:
        encoded = json.dumps(payload, sort_keys=True, indent=2).encode("utf-8") + b"\n"
        path.write_bytes(encoded)
        return len(encoded)
