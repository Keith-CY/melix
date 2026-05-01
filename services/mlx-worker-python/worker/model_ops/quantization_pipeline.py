from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packages.protocol.python.worker.v1 import common_pb2, maintenance_pb2

from worker.model_ops.quantization_profiles import (
    CalibrationPlan,
    QuantizationProfile,
    calibration_plan_for_profile,
    compensation_metadata_for_request,
    hybrid_layout_metadata_for_request,
    normalize_quantization_profile,
    planning_metadata_for_request,
    protected_scope_for_request,
    source_format_metadata_for_request,
    strategy_metadata_for_request,
)
from worker.registry import WorkerRegistry

_BUNDLE_SCHEMA_VERSION = "melix.quantized_bundle.v1"


@dataclass(frozen=True)
class QuantizationPipelineResult:
    bundle_path: Path
    manifest_path: Path
    manifest_payload: dict[str, Any]
    profile: QuantizationProfile
    calibration: CalibrationPlan
    artifact_bytes: int
    manifest_bytes: int
    smoke_test_passed: bool


class OQQuantizationPipeline:
    def __init__(self, registry: WorkerRegistry) -> None:
        self._registry = registry

    def run(
        self,
        request: maintenance_pb2.ConvertModelRequest,
        *,
        job_id: str,
        output_dir: Path,
    ) -> QuantizationPipelineResult:
        source_model = self._resolve_source_model(request.source_model)
        profile = normalize_quantization_profile(request)
        calibration = calibration_plan_for_profile(
            profile,
            source_model=request.source_model,
        )

        bundle_path = (output_dir / job_id / "quantize.artifact").resolve()
        bundle_path.mkdir(parents=True, exist_ok=True)

        files = {
            bundle_path / "config.json": {
                "model_id": source_model.model_id,
                "model_kind": source_model.model_kind,
                "source_model": request.source_model,
                "quant_profile_id": profile.quant_profile_id,
                "quant_algorithm": profile.algorithm,
            },
            bundle_path / "tokenizer.json": {
                "tokenizer_hash": source_model.tokenizer_hash,
                "source_model": request.source_model,
            },
        }
        for path, payload in files.items():
            path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

        weights_path = bundle_path / "weights.safetensors"
        weights_path.write_bytes(
            json.dumps(
                {
                    "model_id": source_model.model_id,
                    "quant_profile_id": profile.quant_profile_id,
                    "weight_quant": profile.weight_quant,
                    "kv_quant": profile.kv_quant,
                    "calibration": calibration.to_dict(),
                },
                sort_keys=True,
            ).encode("utf-8")
        )

        smoke_test_passed = False
        if request.run_smoke_test:
            smoke_test_passed = self._run_structural_smoke_test(bundle_path)

        artifact_bytes = 0
        for entry in os.scandir(bundle_path):
            if entry.name == "manifest.json":
                continue
            if entry.is_file():
                artifact_bytes += entry.stat().st_size

        manifest_path = bundle_path / "manifest.json"
        manifest_payload = self._manifest_payload(
            request=request,
            job_id=job_id,
            source_model=source_model,
            profile=profile,
            calibration=calibration,
            strategy=strategy_metadata_for_request(request, source_model=request.source_model),
            source_format=source_format_metadata_for_request(request, model_kind=source_model.model_kind),
            hybrid_layout=hybrid_layout_metadata_for_request(request),
            planning=planning_metadata_for_request(request),
            compensation=compensation_metadata_for_request(request),
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

        return QuantizationPipelineResult(
            bundle_path=bundle_path,
            manifest_path=manifest_path,
            manifest_payload=manifest_payload,
            profile=profile,
            calibration=calibration,
            artifact_bytes=artifact_bytes,
            manifest_bytes=manifest_payload["manifest_bytes"],
            smoke_test_passed=smoke_test_passed,
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
    def _manifest_payload(
        *,
        request: maintenance_pb2.ConvertModelRequest,
        job_id: str,
        source_model: common_pb2.ModelSpec,
        profile: QuantizationProfile,
        calibration: CalibrationPlan,
        strategy: dict[str, str],
        source_format: dict[str, str],
        hybrid_layout: dict[str, str] | None,
        planning: dict[str, object] | None,
        compensation: dict[str, object] | None,
        bundle_path: Path,
        manifest_path: Path,
        artifact_bytes: int,
        smoke_test_passed: bool,
    ) -> dict[str, Any]:
        payload = {
            "schema_version": _BUNDLE_SCHEMA_VERSION,
            "artifact_kind": "quantized_model_bundle",
            "job_id": job_id,
            "operation": "quantize",
            "source_model": request.source_model,
            "source_model_spec": {
                "model_id": source_model.model_id,
                "model_path": source_model.model_path,
                "model_kind": source_model.model_kind,
                "revision": source_model.revision,
                "tokenizer_hash": source_model.tokenizer_hash,
                "quant_profile_id": source_model.quant_profile_id,
            },
            "artifact_path": str(bundle_path),
            "manifest_path": str(manifest_path),
            "artifact_bytes": artifact_bytes,
            "manifest_bytes": 0,
            "weight_quant": request.weight_quant,
            "kv_quant": request.kv_quant,
            "quant_profile": profile.to_manifest_dict(),
            "calibration": calibration.to_dict(),
            "strategy": strategy,
            "source_format": source_format,
            "compatibility": {
                "runtime": "mlx_text",
                "serving_compatible": True,
                "smoke_test_requested": request.run_smoke_test,
                "smoke_test_passed": smoke_test_passed,
            },
            "protected_scope": protected_scope_for_request(
                request,
                source_model_spec=source_model,
            ),
            "ext": dict(request.ext),
        }
        if hybrid_layout is not None:
            payload["hybrid_layout"] = hybrid_layout
        if planning is not None:
            payload["planning"] = planning
        if compensation is not None:
            payload["compensation"] = compensation
        return payload

    @staticmethod
    def _encode_manifest(payload: dict[str, Any]) -> bytes:
        return json.dumps(payload, sort_keys=True, indent=2).encode("utf-8") + b"\n"

    @staticmethod
    def _manifest_size(payload: dict[str, Any]) -> int:
        return len(OQQuantizationPipeline._encode_manifest(payload))

    @staticmethod
    def _write_manifest(path: Path, payload: dict[str, Any]) -> int:
        encoded = OQQuantizationPipeline._encode_manifest(payload)
        path.write_bytes(encoded)
        return len(encoded)
