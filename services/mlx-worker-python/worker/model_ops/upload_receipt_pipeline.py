from __future__ import annotations

import json
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
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
class PublishResult:
    backend: str
    target_repo: str
    target_url: str
    remote_ref: str
    published_files: list[str]


@dataclass(frozen=True)
class SourceArtifactDescriptor:
    artifact_path: str
    artifact_kind: str
    schema_version: str
    manifest_path: str
    source_model: str
    manifest_payload: dict[str, Any] | None


@dataclass(frozen=True)
class PreparedPublishSource:
    source_path: Path
    published_files: list[str]


class HuggingFacePublishBackend:
    def publish(
        self,
        *,
        source_path: Path,
        target_repo: str,
        artifact_kind: str,
        token: str = "",
        private: bool = False,
        commit_message: str = "",
    ) -> PublishResult:
        resolved_source_path = source_path.expanduser().resolve()
        command = [
            _resolve_hf_cli_command(),
            "upload",
            target_repo,
            str(resolved_source_path),
            "." if resolved_source_path.is_dir() else resolved_source_path.name,
            "--repo-type",
            "model",
            "--quiet",
        ]
        if private:
            command.append("--private")
        if commit_message:
            command.extend(["--commit-message", commit_message])
        if token:
            command.extend(["--token", token])

        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            env=dict(os.environ),
        )
        if process.returncode != 0:
            message = (process.stderr or process.stdout or "Hugging Face publish failed.").strip()
            lowered = message.lower()
            error_code = "publish_auth_required" if "not logged in" in lowered or "token" in lowered else "publish_failed"
            raise ModelOperationError(
                code=error_code,
                message=message,
            )

        remote_ref = ""
        for line in reversed((process.stdout or "").splitlines()):
            stripped = line.strip()
            if stripped:
                remote_ref = stripped
                break

        published_files = (
            sorted(
                str(path.relative_to(resolved_source_path))
                for path in resolved_source_path.rglob("*")
                if path.is_file()
            )
            if resolved_source_path.is_dir()
            else [resolved_source_path.name]
        )
        return PublishResult(
            backend="huggingface_hub",
            target_repo=target_repo,
            target_url=f"https://huggingface.co/{target_repo}",
            remote_ref=remote_ref,
            published_files=published_files,
        )


def _resolve_hf_cli_command() -> str:
    for candidate in ("hf", "huggingface-cli"):
        if shutil.which(candidate):
            return candidate
    return "hf"


class UploadReceiptPipeline:
    def __init__(self, publisher: Any | None = None) -> None:
        self._publisher = publisher or HuggingFacePublishBackend()

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
        target_repo = request.ext.get("target_repo", "").strip()
        if not target_repo:
            raise ModelOperationError(
                code="invalid_argument",
                message="upload requires target_repo.",
            )
        runtime = ""
        source_manifest = descriptor.manifest_payload or {}
        compatibility = source_manifest.get("compatibility")
        if isinstance(compatibility, dict):
            runtime = str(compatibility.get("runtime", "")).strip()

        prepared_source = self._prepare_publish_source(
            descriptor,
            receipt_dir=receipt_path.parent,
            target_repo=target_repo,
        )
        publish_result = self._publisher.publish(
            source_path=prepared_source.source_path,
            target_repo=target_repo,
            artifact_kind=descriptor.artifact_kind,
            token=self._resolve_hf_token(request.ext),
            private=_bool_ext(request.ext, "hf_private"),
            commit_message=self._commit_message(descriptor, target_repo),
        )

        manifest_payload = {
            "schema_version": _UPLOAD_RECEIPT_SCHEMA_VERSION,
            "artifact_kind": "upload_receipt",
            "job_id": job_id,
            "operation": "upload",
            "status": "published",
            "source_model": request.source_model,
            "target_repo": target_repo,
            "artifact_path": descriptor.artifact_path,
            "source_artifact_kind": descriptor.artifact_kind,
            "source_artifact_schema_version": descriptor.schema_version,
            "source_manifest_path": descriptor.manifest_path,
            "source_model_from_artifact": descriptor.source_model,
            "upload_backend": publish_result.backend,
            "upload_duration_ms": (time.perf_counter() - started_at) * 1000.0,
            "published_repo": publish_result.target_repo,
            "published_url": publish_result.target_url,
            "published_ref": publish_result.remote_ref,
            "published_files": prepared_source.published_files or publish_result.published_files,
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

    def _prepare_publish_source(
        self,
        descriptor: SourceArtifactDescriptor,
        *,
        receipt_dir: Path,
        target_repo: str,
    ) -> PreparedPublishSource:
        source_path = Path(descriptor.artifact_path).expanduser().resolve()
        if not source_path.exists():
            raise ModelOperationError(
                code="invalid_artifact",
                message="upload requires a valid local artifact_path.",
            )
        if descriptor.artifact_kind != "adapter" or descriptor.manifest_payload is None:
            if source_path.is_dir():
                published_files = sorted(
                    str(path.relative_to(source_path))
                    for path in source_path.rglob("*")
                    if path.is_file()
                )
            else:
                published_files = [source_path.name]
            return PreparedPublishSource(source_path=source_path, published_files=published_files)

        manifest_payload = dict(descriptor.manifest_payload)
        weights_path = Path(str(manifest_payload.get("weights_path", "")).strip()).expanduser()
        adapter_config_path = Path(str(manifest_payload.get("adapter_config_path", "")).strip()).expanduser()
        if not weights_path.is_file() or not adapter_config_path.is_file():
            raise ModelOperationError(
                code="invalid_artifact",
                message="Adapter publish requires valid weights_path and adapter_config_path.",
            )

        staged_root = receipt_dir / "adapter-bundle"
        staged_root.mkdir(parents=True, exist_ok=True)
        staged_adapter_dir = staged_root / "adapter"
        staged_adapter_dir.mkdir(parents=True, exist_ok=True)

        staged_manifest_name = Path(descriptor.manifest_path).name or "train_lora.adapter.json"
        staged_manifest_path = staged_root / staged_manifest_name
        staged_weights_path = staged_adapter_dir / weights_path.name
        staged_config_path = staged_adapter_dir / adapter_config_path.name
        shutil.copy2(weights_path, staged_weights_path)
        shutil.copy2(adapter_config_path, staged_config_path)

        manifest_payload["artifact_path"] = staged_manifest_name
        manifest_payload["weights_path"] = str(Path("adapter") / staged_weights_path.name)
        manifest_payload["adapter_config_path"] = str(Path("adapter") / staged_config_path.name)
        manifest_payload["published_repo"] = target_repo
        manifest_payload["publish_backend"] = "huggingface_hub"
        manifest_payload["source_manifest_path"] = descriptor.manifest_path
        staged_manifest_path.write_text(json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8")

        return PreparedPublishSource(
            source_path=staged_root,
            published_files=sorted(
                [
                    str(Path("adapter") / staged_weights_path.name),
                    str(Path("adapter") / staged_config_path.name),
                    staged_manifest_name,
                ]
            ),
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

    @staticmethod
    def _commit_message(descriptor: SourceArtifactDescriptor, target_repo: str) -> str:
        artifact_kind = descriptor.artifact_kind or "artifact"
        return f"Publish {artifact_kind} to {target_repo}"

    @staticmethod
    def _resolve_hf_token(ext: dict[str, str]) -> str:
        for key in ("hf_token", "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_HUB_TOKEN"):
            value = ext.get(key, "").strip() or os.environ.get(key, "").strip()
            if value:
                return value
        return ""


def _bool_ext(ext: dict[str, str], key: str) -> bool:
    return ext.get(key, "").strip().lower() in {"1", "true", "yes", "on"}
