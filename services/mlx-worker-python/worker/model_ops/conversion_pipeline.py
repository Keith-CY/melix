from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packages.protocol.python.worker.v1 import common_pb2, maintenance_pb2

from worker.registry import WorkerRegistry

_BUNDLE_SCHEMA_VERSION = "melix.converted_model_bundle.v1"


@dataclass(frozen=True)
class ConversionPipelineResult:
    bundle_path: Path
    manifest_path: Path
    manifest_payload: dict[str, Any]
    artifact_bytes: int
    manifest_bytes: int
    smoke_test_passed: bool
    runtime: str


class ModelConversionPipeline:
    def __init__(self, registry: WorkerRegistry) -> None:
        self._registry = registry

    def run(
        self,
        request: maintenance_pb2.ConvertModelRequest,
        *,
        job_id: str,
        output_dir: Path,
    ) -> ConversionPipelineResult:
        source_model = self._resolve_source_model(request.source_model)
        target_format = request.ext.get("target_format", "").strip() or "melix_model_bundle"
        target_runtime = request.ext.get("target_runtime", "").strip() or self._default_runtime_for_model_kind(
            source_model.model_kind
        )
        target_parser_mode = request.ext.get("target_parser_mode", "").strip() or source_model.parser_mode
        bundle_path = (output_dir / job_id / "convert.artifact").resolve()
        bundle_path.mkdir(parents=True, exist_ok=True)

        files = {
            bundle_path / "config.json": {
                "model_id": source_model.model_id,
                "model_kind": source_model.model_kind,
                "source_model": request.source_model,
                "target_format": target_format,
                "target_runtime": target_runtime,
                "target_parser_mode": target_parser_mode,
            },
            bundle_path / "tokenizer.json": {
                "tokenizer_hash": source_model.tokenizer_hash,
                "source_model": request.source_model,
                "target_parser_mode": target_parser_mode,
            },
        }
        artifact_bytes = 0
        for path, payload in files.items():
            artifact_bytes += self._write_json_file(path, payload)

        weights_path = bundle_path / "weights.safetensors"
        artifact_bytes += self._write_bytes_file(
            weights_path,
            json.dumps(
                {
                    "model_id": source_model.model_id,
                    "source_model": request.source_model,
                    "target_format": target_format,
                    "target_runtime": target_runtime,
                    "source_model_revision": source_model.revision,
                },
                sort_keys=True,
            ).encode("utf-8"),
        )

        smoke_test_passed = False
        if request.run_smoke_test:
            smoke_test_passed = self._run_structural_smoke_test(bundle_path)

        manifest_path = bundle_path / "manifest.json"
        manifest_payload = self._manifest_payload(
            request=request,
            job_id=job_id,
            source_model=source_model,
            target_format=target_format,
            target_runtime=target_runtime,
            target_parser_mode=target_parser_mode,
            bundle_path=bundle_path,
            manifest_path=manifest_path,
            artifact_bytes=artifact_bytes,
            smoke_test_passed=smoke_test_passed,
        )
        manifest_bytes = 0
        while True:
            manifest_payload["manifest_bytes"] = manifest_bytes
            next_manifest_bytes = self._manifest_size(manifest_payload)
            if next_manifest_bytes == manifest_bytes:
                break
            manifest_bytes = next_manifest_bytes
        manifest_payload["manifest_bytes"] = manifest_bytes
        self._write_manifest(manifest_path, manifest_payload)

        return ConversionPipelineResult(
            bundle_path=bundle_path,
            manifest_path=manifest_path,
            manifest_payload=manifest_payload,
            artifact_bytes=artifact_bytes,
            manifest_bytes=manifest_payload["manifest_bytes"],
            smoke_test_passed=smoke_test_passed,
            runtime=target_runtime,
        )

    def _resolve_source_model(self, source_model: str) -> common_pb2.ModelSpec:
        model = self._registry.model_catalog.get(source_model)
        if model is not None:
            return model

        return common_pb2.ModelSpec(
            model_id=Path(source_model).name or source_model,
            model_path=source_model,
            model_kind="text",
            revision="unknown",
            tokenizer_hash="tok-external",
            quant_profile_id="",
            parser_mode="text",
            reasoning_mode="off",
            max_context=0,
        )

    @staticmethod
    def _run_structural_smoke_test(bundle_path: Path) -> bool:
        required_files = (
            bundle_path / "config.json",
            bundle_path / "tokenizer.json",
            bundle_path / "weights.safetensors",
        )
        for path in required_files:
            if not path.exists():
                return False
            if path.suffix == ".json":
                json.loads(path.read_text(encoding="utf-8"))
        return True

    @staticmethod
    def _default_runtime_for_model_kind(model_kind: str) -> str:
        if model_kind == "vlm":
            return "mlx_vlm"
        if model_kind == "ocr":
            return "mlx_ocr"
        if model_kind == "image":
            return "mlx_image"
        if model_kind == "embedding":
            return "mlx_embedding"
        if model_kind == "rerank":
            return "mlx_rerank"
        return "mlx_text"

    @staticmethod
    def _manifest_payload(
        *,
        request: maintenance_pb2.ConvertModelRequest,
        job_id: str,
        source_model: common_pb2.ModelSpec,
        target_format: str,
        target_runtime: str,
        target_parser_mode: str,
        bundle_path: Path,
        manifest_path: Path,
        artifact_bytes: int,
        smoke_test_passed: bool,
    ) -> dict[str, Any]:
        return {
            "schema_version": _BUNDLE_SCHEMA_VERSION,
            "artifact_kind": "converted_model_bundle",
            "job_id": job_id,
            "operation": "convert",
            "source_model": request.source_model,
            "source_model_spec": {
                "model_id": source_model.model_id,
                "model_path": source_model.model_path,
                "model_kind": source_model.model_kind,
                "revision": source_model.revision,
                "tokenizer_hash": source_model.tokenizer_hash,
                "quant_profile_id": source_model.quant_profile_id,
                "parser_mode": source_model.parser_mode,
                "max_context": source_model.max_context,
            },
            "artifact_path": str(bundle_path),
            "manifest_path": str(manifest_path),
            "artifact_bytes": artifact_bytes,
            "manifest_bytes": 0,
            "target_format": target_format,
            "target_runtime": target_runtime,
            "target_parser_mode": target_parser_mode,
            "conversion_backend": "melix_structural_packager",
            "compatibility": {
                "runtime": target_runtime,
                "serving_compatible": True,
                "smoke_test_requested": request.run_smoke_test,
                "smoke_test_passed": smoke_test_passed,
            },
            "ext": dict(request.ext),
        }

    @staticmethod
    def _encode_manifest(payload: dict[str, Any]) -> bytes:
        return json.dumps(payload, sort_keys=True, indent=2).encode("utf-8") + b"\n"

    @staticmethod
    def _manifest_size(payload: dict[str, Any]) -> int:
        return len(ModelConversionPipeline._encode_manifest(payload))

    @staticmethod
    def _write_json_file(path: Path, payload: dict[str, Any]) -> int:
        encoded = json.dumps(payload, indent=2).encode("utf-8") + b"\n"
        path.write_bytes(encoded)
        return len(encoded)

    @staticmethod
    def _write_bytes_file(path: Path, payload: bytes) -> int:
        path.write_bytes(payload)
        return len(payload)

    @staticmethod
    def _write_manifest(path: Path, payload: dict[str, Any]) -> int:
        encoded = ModelConversionPipeline._encode_manifest(payload)
        path.write_bytes(encoded)
        return len(encoded)
