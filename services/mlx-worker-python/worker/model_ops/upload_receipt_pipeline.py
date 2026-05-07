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


_ADAPTER_EXPORT_KINDS = {"adapter", "adapter_export"}
_MERGED_EXPORT_KINDS = {"merged", "merged_export", "converted_model_bundle"}
_PROCESSOR_CONFIG_FILENAMES = frozenset({
    "processor_config.json",
    "preprocessor_config.json",
    "image_processor.json",
})


def _last_nonblank_line(value: str) -> str:
    end = len(value)
    while end > 0:
        line_start = value.rfind("\n", 0, end) + 1
        stripped = value[line_start:end].strip()
        if stripped:
            return stripped
        end = line_start - 1
    return ""


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
        published_files: list[str] | None = None,
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

        remote_ref = _last_nonblank_line(process.stdout or "")

        if published_files is None:
            if resolved_source_path.is_dir():
                published_files = _collect_published_file_list(resolved_source_path)
            else:
                published_files = [resolved_source_path.name]

        return PublishResult(
            backend="huggingface_hub",
            target_repo=target_repo,
            target_url=f"https://huggingface.co/{target_repo}",
            remote_ref=remote_ref,
            published_files=published_files,
        )


@dataclass(frozen=True)
class LocalFilesystemPublishBackend:
    root: Path

    def publish(
        self,
        *,
        source_path: Path,
        target_repo: str,
        artifact_kind: str,
        token: str = "",
        private: bool = False,
        commit_message: str = "",
        published_files: list[str] | None = None,
    ) -> PublishResult:
        del artifact_kind, token, private, commit_message
        resolved_source_path = source_path.expanduser().resolve()
        target_path = self.root.expanduser().resolve() / _local_target_repo_path(target_repo)
        if target_path.exists() and not target_path.is_dir():
            target_path.unlink()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if resolved_source_path.is_dir():
            shutil.copytree(resolved_source_path, target_path, dirs_exist_ok=True)
        else:
            target_path.mkdir(parents=True, exist_ok=True)
            shutil.copy2(resolved_source_path, target_path / resolved_source_path.name)

        if published_files is None:
            if target_path.is_dir():
                published_files = _collect_published_file_list(target_path)
            else:
                published_files = [target_path.name]

        return PublishResult(
            backend="local_filesystem",
            target_repo=target_repo,
            target_url=target_path.as_uri(),
            remote_ref=str(target_path),
            published_files=published_files,
        )


def _local_target_repo_path(target_repo: str) -> Path:
    normalized_parts = [
        part.strip().replace("\\", "_")
        for part in target_repo.split("/")
        if part.strip() not in {"", ".", ".."}
    ]
    if not normalized_parts:
        normalized_parts = ["artifact"]
    return Path(*normalized_parts)


def _resolve_hf_cli_command() -> str:
    for candidate in ("hf", "huggingface-cli"):
        if shutil.which(candidate):
            return candidate
    return "hf"


def _collect_published_file_list(source_dir: Path) -> list[str]:
    source_dir_str = os.fspath(source_dir)
    pending: list[tuple[str, str]] = [(source_dir_str, "")]
    published_files: list[str] = []
    while pending:
        current_dir, relative_dir = pending.pop()
        with os.scandir(current_dir) as entries:
            for entry in entries:
                relative_path = entry.name if not relative_dir else f"{relative_dir}/{entry.name}"
                if entry.is_dir(follow_symlinks=False):
                    pending.append((entry.path, relative_path))
                elif entry.is_file(follow_symlinks=False):
                    published_files.append(relative_path)
                elif not entry.is_dir(follow_symlinks=True):
                    published_files.append(relative_path)
    return sorted(published_files)


class UploadReceiptPipeline:
    @staticmethod
    def _collect_published_file_list(source_dir: Path) -> list[str]:
        return _collect_published_file_list(source_dir)

    def __init__(self, publisher: Any | None = None) -> None:
        self._publisher = publisher

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
        export_artifact_kind = self._resolve_export_artifact_kind(
            descriptor=descriptor,
            requested_kind=request.ext.get("artifact_kind", "").strip(),
        )
        compatibility = source_manifest.get("compatibility")
        if isinstance(compatibility, dict):
            runtime = str(compatibility.get("runtime", "")).strip()

        prepared_source = self._prepare_publish_source(
            descriptor,
            receipt_dir=receipt_path.parent,
            target_repo=target_repo,
            export_artifact_kind=export_artifact_kind,
        )
        processor_config_files = UploadReceiptPipeline._collect_processor_config_files(
            prepared_source.published_files
        )
        publish_result = self._resolve_publisher(request.ext).publish(
            source_path=prepared_source.source_path,
            target_repo=target_repo,
            artifact_kind=export_artifact_kind,
            token=self._resolve_hf_token(request.ext),
            private=_bool_ext(request.ext, "hf_private"),
            commit_message=self._commit_message(descriptor, target_repo),
            published_files=prepared_source.published_files,
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
            "export_artifact_kind": export_artifact_kind,
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
            parent_lineage = self._parent_lineage(
                descriptor=descriptor,
                source_manifest=source_manifest,
                export_artifact_kind=export_artifact_kind,
            )
            if parent_lineage:
                manifest_payload["parent_lineage"] = parent_lineage
            if descriptor.artifact_kind == "adapter":
                manifest_payload["adapter_name"] = str(source_manifest.get("adapter_name", ""))
                manifest_payload["source_adapter_job_id"] = str(source_manifest.get("job_id", ""))
                manifest_payload["distribution_contract"] = "adapter_only"
            if descriptor.artifact_kind == "converted_model_bundle":
                manifest_payload["target_format"] = str(source_manifest.get("target_format", ""))
                manifest_payload["conversion_backend"] = str(source_manifest.get("conversion_backend", ""))
            if descriptor.schema_version == "melix.derived_text_model.v1":
                manifest_payload["derived_model_id"] = str(source_manifest.get("derived_model_id", ""))
                manifest_payload["source_activation_job_id"] = str(source_manifest.get("job_id", ""))
                manifest_payload["activation_mode"] = str(source_manifest.get("activation_mode", ""))
            if export_artifact_kind == "merged_export":
                if processor_config_files:
                    manifest_payload["distribution_contract"] = "merged_multimodal"
                    manifest_payload["processor_config_files"] = processor_config_files
                else:
                    manifest_payload["distribution_contract"] = "merged_model"

        manifest_bytes = 0
        artifact_bytes = 0
        while True:
            manifest_payload["manifest_path"] = str(receipt_path)
            manifest_payload["bundle_path"] = str(receipt_path)
            manifest_payload["manifest_bytes"] = manifest_bytes
            manifest_payload["artifact_bytes"] = artifact_bytes
            next_manifest_bytes = self._manifest_size(manifest_payload)
            next_artifact_bytes = next_manifest_bytes
            if next_manifest_bytes == manifest_bytes and next_artifact_bytes == artifact_bytes:
                break
            manifest_bytes = next_manifest_bytes
            artifact_bytes = next_artifact_bytes
        manifest_payload["manifest_bytes"] = manifest_bytes
        manifest_payload["artifact_bytes"] = artifact_bytes
        self._write_manifest(receipt_path, manifest_payload)

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
        export_artifact_kind: str,
    ) -> PreparedPublishSource:
        source_path = Path(descriptor.artifact_path).expanduser().resolve()
        if not source_path.exists():
            raise ModelOperationError(
                code="invalid_artifact",
                message="upload requires a valid local artifact_path.",
            )
        if export_artifact_kind == "merged_export":
            merged_source = self._resolve_merged_publish_source(descriptor, source_path)
            published_files = self._collect_published_file_list(merged_source)
            return PreparedPublishSource(source_path=merged_source, published_files=published_files)

        if descriptor.artifact_kind != "adapter" or descriptor.manifest_payload is None:
            if source_path.is_dir():
                published_files = self._collect_published_file_list(source_path)
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

    @staticmethod
    def _resolve_publisher_from_ext(ext: dict[str, str]) -> Any:
        backend = ext.get("publish_backend", "").strip().lower()
        if backend in {"", "huggingface", "huggingface_hub"}:
            return HuggingFacePublishBackend()
        if backend in {"local", "local_filesystem", "filesystem"}:
            root = ext.get("local_publish_root", "").strip()
            if not root:
                raise ModelOperationError(
                    code="invalid_argument",
                    message="local_filesystem publish requires local_publish_root.",
                )
            return LocalFilesystemPublishBackend(root=Path(root))
        raise ModelOperationError(
            code="unsupported_publish_backend",
            message="publish_backend must be one of: huggingface_hub, local_filesystem.",
        )

    def _resolve_publisher(self, ext: dict[str, str]) -> Any:
        if self._publisher is not None:
            return self._publisher
        return self._resolve_publisher_from_ext(ext)

    @staticmethod
    def _resolve_export_artifact_kind(
        *,
        descriptor: SourceArtifactDescriptor,
        requested_kind: str,
    ) -> str:
        normalized_requested = requested_kind.strip()
        if normalized_requested in _ADAPTER_EXPORT_KINDS:
            if descriptor.artifact_kind != "adapter":
                raise ModelOperationError(
                    code="invalid_argument",
                    message="Adapter export requires an adapter artifact_path.",
                )
            return "adapter_export"
        if normalized_requested in _MERGED_EXPORT_KINDS:
            if UploadReceiptPipeline._is_merged_publishable_descriptor(descriptor) is False:
                raise ModelOperationError(
                    code="invalid_argument",
                    message="Merged export requires a fused derived-model artifact or converted model bundle.",
                )
            return "merged_export"
        if descriptor.artifact_kind == "adapter":
            return "adapter_export"
        if UploadReceiptPipeline._is_merged_publishable_descriptor(descriptor):
            return "merged_export"
        return "model_export"

    @staticmethod
    def _is_merged_publishable_descriptor(descriptor: SourceArtifactDescriptor) -> bool:
        if descriptor.artifact_kind == "converted_model_bundle":
            return True
        manifest_payload = descriptor.manifest_payload or {}
        return (
            descriptor.schema_version == "melix.derived_text_model.v1"
            and str(manifest_payload.get("activation_mode", "")).strip() == "fused_derived_model"
        )

    @staticmethod
    def _resolve_merged_publish_source(
        descriptor: SourceArtifactDescriptor,
        source_path: Path,
    ) -> Path:
        if source_path.is_dir():
            return source_path
        manifest_payload = descriptor.manifest_payload or {}
        if descriptor.artifact_kind == "converted_model_bundle" and source_path.is_file():
            parent_dir = source_path.parent
            if (parent_dir / "manifest.json").is_file():
                return parent_dir
        if descriptor.schema_version == "melix.derived_text_model.v1":
            activation_mode = str(manifest_payload.get("activation_mode", "")).strip()
            derived_model_path = Path(str(manifest_payload.get("derived_model_path", "")).strip()).expanduser()
            if activation_mode != "fused_derived_model":
                raise ModelOperationError(
                    code="invalid_argument",
                    message="Merged export requires a fused derived-model activation output.",
                )
            if derived_model_path.is_dir():
                return derived_model_path.resolve()
        raise ModelOperationError(
            code="invalid_artifact",
            message="Merged export requires a publishable local directory.",
        )

    @staticmethod
    def _parent_lineage(
        *,
        descriptor: SourceArtifactDescriptor,
        source_manifest: dict[str, Any],
        export_artifact_kind: str,
    ) -> dict[str, Any]:
        parent_lineage = {
            "local_artifact_path": descriptor.artifact_path,
            "local_manifest_path": descriptor.manifest_path,
            "source_artifact_kind": descriptor.artifact_kind,
            "source_schema_version": descriptor.schema_version,
            "source_job_id": str(source_manifest.get("job_id", "")).strip(),
            "source_model": descriptor.source_model,
            "export_artifact_kind": export_artifact_kind,
        }
        if descriptor.schema_version == "melix.derived_text_model.v1":
            parent_lineage["derived_model_id"] = str(source_manifest.get("derived_model_id", "")).strip()
            parent_lineage["activation_mode"] = str(source_manifest.get("activation_mode", "")).strip()
            parent_lineage["source_adapter_job_id"] = str(source_manifest.get("source_adapter_job_id", "")).strip()
        return {key: value for key, value in parent_lineage.items() if value not in {"", None}}

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

        inferred_artifact_kind = self._inferred_artifact_kind_from_manifest(manifest_payload)
        return SourceArtifactDescriptor(
            artifact_path=str(artifact_path),
            artifact_kind=inferred_artifact_kind or str(manifest_payload.get("artifact_kind", "")).strip() or requested_kind or "model",
            schema_version=str(manifest_payload.get("schema_version", "")).strip(),
            manifest_path=str(manifest_path),
            source_model=str(manifest_payload.get("source_model", "")).strip(),
            manifest_payload=manifest_payload,
        )

    @staticmethod
    def _inferred_artifact_kind_from_manifest(manifest_payload: dict[str, Any]) -> str:
        schema_version = str(manifest_payload.get("schema_version", "")).strip()
        if schema_version == "melix.derived_text_model.v1":
            return "derived_text_model"
        return ""

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
    def _collect_processor_config_files(published_files: list[str]) -> list[str]:
        return sorted(f for f in published_files if "/" not in f and f in _PROCESSOR_CONFIG_FILENAMES)

    @staticmethod
    def _encode_manifest(payload: dict[str, Any]) -> bytes:
        return json.dumps(payload, sort_keys=True, indent=2).encode("utf-8") + b"\n"

    @staticmethod
    def _manifest_size(payload: dict[str, Any]) -> int:
        return len(UploadReceiptPipeline._encode_manifest(payload))

    @staticmethod
    def _write_manifest(path: Path, payload: dict[str, Any]) -> int:
        encoded = UploadReceiptPipeline._encode_manifest(payload)
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
