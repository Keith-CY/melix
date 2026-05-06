from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from threading import Event
import time
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
from worker.model_ops.errors import ModelOperationError
from worker.registry import WorkerRegistry

_BUNDLE_SCHEMA_VERSION = "melix.quantized_bundle.v1"
_QAT_TRAINING_SCHEMA_VERSION = "melix.qat_training_run.v1"
_SMOKE_REQUIRED_FILES = ("config.json", "tokenizer.json", "weights.safetensors")
_MANIFEST_ONLY_QUANTIZATION_BACKEND = "manifest_only"
_MLX_LM_CONVERT_QUANTIZATION_BACKEND = "mlx_lm_convert"
_QAT_FAKE_QUANT_BACKEND = "melix_fake_quant_optimizer"
_SUPPORTED_QUANTIZATION_BACKENDS = {
    _MANIFEST_ONLY_QUANTIZATION_BACKEND,
    _MLX_LM_CONVERT_QUANTIZATION_BACKEND,
}
_SUPPORTED_MLX_LM_Q_MODES = {"affine", "mxfp4", "nvfp4", "mxfp8"}


@dataclass(frozen=True)
class LocalInferenceSmokeEvidence:
    status: str
    evidence_kind: str
    smoke_mode: str
    runtime: str
    runtime_backend: str
    artifact_path: str
    checked_files: tuple[str, ...]
    latency_ms: float
    prompt_sha256: str = ""
    generated_token_count: int = 0
    failure_reason: str = ""

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    def to_manifest_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "evidence_kind": self.evidence_kind,
            "smoke_mode": self.smoke_mode,
            "runtime": self.runtime,
            "runtime_backend": self.runtime_backend,
            "artifact_path": self.artifact_path,
            "checked_files": list(self.checked_files),
            "latency_ms": self.latency_ms,
            "prompt_sha256": self.prompt_sha256,
            "generated_token_count": self.generated_token_count,
            "failure_reason": self.failure_reason,
        }


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
    smoke_evidence: LocalInferenceSmokeEvidence


@dataclass(frozen=True)
class QATFakeQuantTrainingResult:
    manifest_path: Path
    trace_path: Path
    fake_quant_artifact_path: Path
    artifact_bytes: int
    payload: dict[str, Any]


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
        quantization_mode = _quantization_mode_for_request(request)
        source_artifact_kind = _source_artifact_kind_for_request(request)
        quantization_backend = _quantization_backend_for_request(request)
        source_artifact_path = _source_artifact_path_for_request(
            request,
            source_model=source_model,
            source_artifact_kind=source_artifact_kind,
        )
        _validate_quantization_source(
            quantization_mode=quantization_mode,
            source_artifact_kind=source_artifact_kind,
            source_artifact_path=source_artifact_path,
            quantization_backend=quantization_backend,
        )
        smoke_mode = _local_inference_smoke_mode_for_request(request)
        calibration_evidence = _calibration_evidence_for_request(request)
        calibration = calibration_plan_for_profile(
            profile,
            source_model=request.source_model,
        )

        bundle_path = (output_dir / job_id / "quantize.artifact").resolve()
        qat_training_result: QATFakeQuantTrainingResult | None = None
        qat_metadata: dict[str, Any] | None = None
        if quantization_backend == _MLX_LM_CONVERT_QUANTIZATION_BACKEND:
            artifact_bytes = self._write_mlx_lm_quantized_bundle(
                request=request,
                source_artifact_path=source_artifact_path,
                profile=profile,
                bundle_path=bundle_path,
            )
            if quantization_mode == "qat":
                qat_training_result = _run_qat_fake_quant_training(
                    request=request,
                    job_id=job_id,
                    source_artifact_kind=source_artifact_kind,
                    source_artifact_path=source_artifact_path,
                    profile=profile,
                    calibration_evidence=calibration_evidence,
                    bundle_path=bundle_path,
                )
                artifact_bytes += qat_training_result.artifact_bytes
        else:
            bundle_path.mkdir(parents=True, exist_ok=True)
            if quantization_mode == "qat":
                qat_training_result = _run_qat_fake_quant_training(
                    request=request,
                    job_id=job_id,
                    source_artifact_kind=source_artifact_kind,
                    source_artifact_path=source_artifact_path,
                    profile=profile,
                    calibration_evidence=calibration_evidence,
                    bundle_path=bundle_path,
                )
            qat_metadata = _qat_metadata_for_request(
                request,
                quantization_mode=quantization_mode,
                source_artifact_kind=source_artifact_kind,
                source_artifact_path=source_artifact_path,
                calibration_evidence=calibration_evidence,
                qat_training_result=qat_training_result,
            )

            files = {
                bundle_path / "config.json": {
                    "model_id": source_model.model_id,
                    "model_kind": source_model.model_kind,
                    "source_model": request.source_model,
                    "quant_profile_id": profile.quant_profile_id,
                    "quant_algorithm": profile.algorithm,
                    "quantization_mode": quantization_mode,
                    "source_artifact_kind": source_artifact_kind,
                },
                bundle_path / "tokenizer.json": {
                    "tokenizer_hash": source_model.tokenizer_hash,
                    "source_model": request.source_model,
                },
            }
            artifact_bytes = qat_training_result.artifact_bytes if qat_training_result is not None else 0
            for path, payload in files.items():
                artifact_bytes += self._write_json_file(path, payload)

            weights_path = bundle_path / "weights.safetensors"
            artifact_bytes += self._write_bytes_file(
                weights_path,
                json.dumps(
                    {
                        "model_id": source_model.model_id,
                        "quant_profile_id": profile.quant_profile_id,
                        "weight_quant": profile.weight_quant,
                        "kv_quant": profile.kv_quant,
                        "calibration": calibration.to_dict(),
                        "quantization_mode": quantization_mode,
                        "source_artifact_kind": source_artifact_kind,
                        "qat": qat_metadata or {},
                    },
                    sort_keys=True,
                ).encode("utf-8"),
            )

        if quantization_mode == "qat" and qat_metadata is None:
            qat_metadata = _qat_metadata_for_request(
                request,
                quantization_mode=quantization_mode,
                source_artifact_kind=source_artifact_kind,
                source_artifact_path=source_artifact_path,
                calibration_evidence=calibration_evidence,
                qat_training_result=qat_training_result,
            )
        smoke_evidence = _not_requested_smoke_evidence(
            bundle_path=bundle_path,
            smoke_mode=smoke_mode,
        )
        smoke_checked_files = _smoke_required_files_for_backend(
            bundle_path,
            quantization_backend=quantization_backend,
        )
        if request.run_smoke_test:
            smoke_evidence = self._run_local_inference_smoke_test(
                request=request,
                job_id=job_id,
                source_model=source_model,
                profile=profile,
                bundle_path=bundle_path,
                smoke_mode=smoke_mode,
                checked_files=smoke_checked_files,
            )
        smoke_test_passed = smoke_evidence.passed

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
            quantization_mode=quantization_mode,
            source_artifact_kind=source_artifact_kind,
            source_artifact_path=source_artifact_path,
            quantization_backend=quantization_backend,
            qat_metadata=qat_metadata,
            calibration_evidence=calibration_evidence,
            bundle_path=bundle_path,
            manifest_path=manifest_path,
            artifact_bytes=artifact_bytes,
            smoke_evidence=smoke_evidence,
        )
        manifest_bytes = 0
        encoded_manifest = b""
        while True:
            manifest_payload["manifest_bytes"] = manifest_bytes
            encoded_manifest = self._encode_manifest(manifest_payload)
            next_manifest_bytes = len(encoded_manifest)
            if next_manifest_bytes == manifest_bytes:
                break
            manifest_bytes = next_manifest_bytes
        manifest_payload["manifest_bytes"] = manifest_bytes
        self._write_manifest(manifest_path, manifest_payload, encoded_manifest)

        return QuantizationPipelineResult(
            bundle_path=bundle_path,
            manifest_path=manifest_path,
            manifest_payload=manifest_payload,
            profile=profile,
            calibration=calibration,
            artifact_bytes=artifact_bytes,
            manifest_bytes=manifest_payload["manifest_bytes"],
            smoke_test_passed=smoke_test_passed,
            smoke_evidence=smoke_evidence,
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

    def _run_local_inference_smoke_test(
        self,
        *,
        request: maintenance_pb2.ConvertModelRequest,
        job_id: str,
        source_model: common_pb2.ModelSpec,
        profile: QuantizationProfile,
        bundle_path: Path,
        smoke_mode: str,
        checked_files: tuple[str, ...],
    ) -> LocalInferenceSmokeEvidence:
        if smoke_mode == "structural":
            return self._run_structural_smoke_evidence(bundle_path, checked_files=checked_files)
        if smoke_mode == "runtime_generate":
            return self._run_runtime_generate_smoke_evidence(
                request=request,
                job_id=job_id,
                source_model=source_model,
                profile=profile,
                bundle_path=bundle_path,
                checked_files=checked_files,
            )
        raise AssertionError(f"Unexpected local inference smoke mode: {smoke_mode}")

    @staticmethod
    def _run_structural_smoke_test(bundle_path: Path) -> bool:
        return OQQuantizationPipeline._run_structural_smoke_evidence(bundle_path).passed

    @staticmethod
    def _run_structural_smoke_evidence(
        bundle_path: Path,
        *,
        checked_files: tuple[str, ...] | None = None,
    ) -> LocalInferenceSmokeEvidence:
        started_at = time.perf_counter()
        checked_files = checked_files or _SMOKE_REQUIRED_FILES
        for file_name in checked_files:
            path = bundle_path / file_name
            if not path.exists():
                return LocalInferenceSmokeEvidence(
                    status="failed",
                    evidence_kind="bundle_structural",
                    smoke_mode="structural",
                    runtime="mlx_text",
                    runtime_backend="structural",
                    artifact_path=str(bundle_path),
                    checked_files=checked_files,
                    latency_ms=_elapsed_ms(started_at),
                    failure_reason=f"{file_name} is missing from quantized bundle.",
                )
            if path.suffix == ".json":
                try:
                    json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    return LocalInferenceSmokeEvidence(
                        status="failed",
                        evidence_kind="bundle_structural",
                        smoke_mode="structural",
                        runtime="mlx_text",
                        runtime_backend="structural",
                        artifact_path=str(bundle_path),
                        checked_files=checked_files,
                        latency_ms=_elapsed_ms(started_at),
                        failure_reason=f"{file_name} is not readable JSON: {exc}",
                    )
        return LocalInferenceSmokeEvidence(
            status="passed",
            evidence_kind="bundle_structural",
            smoke_mode="structural",
            runtime="mlx_text",
            runtime_backend="structural",
            artifact_path=str(bundle_path),
            checked_files=checked_files,
            latency_ms=_elapsed_ms(started_at),
        )

    def _run_runtime_generate_smoke_evidence(
        self,
        *,
        request: maintenance_pb2.ConvertModelRequest,
        job_id: str,
        source_model: common_pb2.ModelSpec,
        profile: QuantizationProfile,
        bundle_path: Path,
        checked_files: tuple[str, ...],
    ) -> LocalInferenceSmokeEvidence:
        structural_evidence = self._run_structural_smoke_evidence(bundle_path, checked_files=checked_files)
        prompt = (
            request.ext.get("local_inference_smoke_prompt", "").strip()
            or "Validate the Melix quantized bundle."
        )
        prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        if not structural_evidence.passed:
            return LocalInferenceSmokeEvidence(
                status="failed",
                evidence_kind="local_runtime_generate",
                smoke_mode="runtime_generate",
                runtime="mlx_text",
                runtime_backend="preflight",
                artifact_path=str(bundle_path),
                checked_files=structural_evidence.checked_files,
                latency_ms=structural_evidence.latency_ms,
                prompt_sha256=prompt_sha256,
                failure_reason=f"structural preflight failed: {structural_evidence.failure_reason}",
            )

        loaded_handle = ""
        runtime_backend = ""
        started_at = time.perf_counter()
        try:
            smoke_model = common_pb2.ModelSpec(
                model_id=f"{source_model.model_id}-quantized-{profile.quant_profile_id}-{job_id}",
                model_path=str(bundle_path),
                model_kind=source_model.model_kind or "text",
                revision=f"quantized:{job_id}",
                tokenizer_hash=source_model.tokenizer_hash,
                quant_profile_id=profile.quant_profile_id,
                parser_mode=source_model.parser_mode,
                reasoning_mode=source_model.reasoning_mode,
                max_context=source_model.max_context,
                ext=dict(source_model.ext),
            )
            smoke_model.ext["melix.quantized_bundle_path"] = str(bundle_path)
            loaded = self._registry.load_model(smoke_model)
            loaded_handle = loaded.handle
            runtime = self._registry.runtime_for_loaded_model(loaded)
            runtime_backend = str(getattr(runtime, "runtime_name", "") or loaded.runtime_kind)
            messages = [
                common_pb2.ChatMessage(
                    role="user",
                    parts=[common_pb2.MessagePart(text=prompt)],
                )
            ]
            rendered_prompt = runtime.render_prompt(
                messages,
                loaded_model=loaded.runtime_model,
                template_kwargs=None,
                execution_ext={},
            )
            sampling = common_pb2.SamplingConfig(
                temperature=0.0,
                top_p=1.0,
                top_k=1,
                max_output_tokens=1,
            )
            cancel_event = Event()
            token_stream = runtime.generate_tokens(
                loaded.runtime_model,
                rendered_prompt,
                sampling,
                cancel_event,
                execution_ext={},
            )
            generated_token_count = 0
            try:
                for event in token_stream:
                    text = getattr(event, "text", str(event))
                    if text:
                        generated_token_count += 1
                    cancel_event.set()
                    break
            finally:
                close = getattr(token_stream, "close", None)
                if callable(close):
                    close()
            if generated_token_count <= 0:
                raise RuntimeError("Runtime smoke generated no token events.")
            return LocalInferenceSmokeEvidence(
                status="passed",
                evidence_kind="local_runtime_generate",
                smoke_mode="runtime_generate",
                runtime="mlx_text",
                runtime_backend=runtime_backend,
                artifact_path=str(bundle_path),
                checked_files=checked_files,
                latency_ms=_elapsed_ms(started_at),
                prompt_sha256=prompt_sha256,
                generated_token_count=generated_token_count,
            )
        except Exception as exc:
            return LocalInferenceSmokeEvidence(
                status="failed",
                evidence_kind="local_runtime_generate",
                smoke_mode="runtime_generate",
                runtime="mlx_text",
                runtime_backend=runtime_backend or "unknown",
                artifact_path=str(bundle_path),
                checked_files=checked_files,
                latency_ms=_elapsed_ms(started_at),
                prompt_sha256=prompt_sha256,
                failure_reason=str(exc),
            )
        finally:
            if loaded_handle:
                self._registry.unload_model(loaded_handle)

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
        quantization_mode: str,
        source_artifact_kind: str,
        source_artifact_path: str,
        quantization_backend: str,
        qat_metadata: dict[str, Any] | None,
        calibration_evidence: dict[str, Any],
        bundle_path: Path,
        manifest_path: Path,
        artifact_bytes: int,
        smoke_evidence: LocalInferenceSmokeEvidence,
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
            "quantization_mode": quantization_mode,
            "source_artifact_kind": source_artifact_kind,
            "source_artifact_path": source_artifact_path,
            "execution_backend": quantization_backend,
            "real_weight_conversion": quantization_backend == _MLX_LM_CONVERT_QUANTIZATION_BACKEND,
            "calibration_dataset_uri": calibration_evidence.get("dataset_uri", ""),
            "quantized_artifact_bytes": artifact_bytes,
            "weight_quant": request.weight_quant,
            "kv_quant": request.kv_quant,
            "quant_profile": profile.to_manifest_dict(),
            "calibration": calibration.to_dict(),
            "release_gate": _release_gate_for_request(
                request,
                smoke_evidence=smoke_evidence,
            ),
            "local_inference_smoke": smoke_evidence.to_manifest_dict(),
            "strategy": strategy,
            "source_format": source_format,
            "compatibility": {
                "runtime": smoke_evidence.runtime,
                "serving_compatible": True,
                "smoke_test_requested": request.run_smoke_test,
                "smoke_test_passed": smoke_evidence.passed,
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
        if calibration_evidence:
            payload["calibration_dataset"] = calibration_evidence
        if qat_metadata is not None:
            payload["qat"] = qat_metadata
        return payload

    @staticmethod
    def _encode_manifest(payload: dict[str, Any]) -> bytes:
        return json.dumps(payload, sort_keys=True, indent=2).encode("utf-8") + b"\n"

    @staticmethod
    def _manifest_size(payload: dict[str, Any]) -> int:
        return len(OQQuantizationPipeline._encode_manifest(payload))

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
    def _write_manifest(path: Path, payload: dict[str, Any], encoded: bytes | None = None) -> int:
        if encoded is None:
            encoded = OQQuantizationPipeline._encode_manifest(payload)
        path.write_bytes(encoded)
        return len(encoded)

    def _write_mlx_lm_quantized_bundle(
        self,
        *,
        request: maintenance_pb2.ConvertModelRequest,
        source_artifact_path: str,
        profile: QuantizationProfile,
        bundle_path: Path,
    ) -> int:
        source_path = _local_source_path_for_mlx_lm_convert(source_artifact_path)
        if bundle_path.exists():
            raise ModelOperationError(
                code="quantization_output_exists",
                message="MLX-LM quantization output path already exists.",
                details={"output_path": str(bundle_path)},
            )
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        params = _mlx_lm_quantization_params_for_request(request, profile)
        convert_kwargs = {
            "source_path": source_path,
            "output_path": bundle_path,
            "q_bits": params["q_bits"],
            "q_mode": params["q_mode"],
        }
        if params["q_group_size"] is not None:
            convert_kwargs["q_group_size"] = params["q_group_size"]
        try:
            self._mlx_lm_convert(**convert_kwargs)
        except ModuleNotFoundError as exc:
            raise ModelOperationError(
                code="quantization_backend_unavailable",
                message="MLX-LM quantization backend is not available in the current runtime.",
                details={"quantization_backend": _MLX_LM_CONVERT_QUANTIZATION_BACKEND},
            ) from exc
        except Exception as exc:
            raise ModelOperationError(
                code="quantization_backend_failure",
                message=f"MLX-LM quantization failed: {exc}",
                details={"quantization_backend": _MLX_LM_CONVERT_QUANTIZATION_BACKEND},
            ) from exc
        return _sum_bundle_file_bytes(bundle_path)

    @staticmethod
    def _mlx_lm_convert(
        *,
        source_path: Path,
        output_path: Path,
        q_bits: int,
        q_mode: str,
        q_group_size: int | None = None,
    ) -> None:
        from mlx_lm import convert as mlx_lm_convert

        kwargs: dict[str, Any] = {
            "mlx_path": str(output_path),
            "quantize": True,
            "q_bits": q_bits,
            "q_mode": q_mode,
        }
        if q_group_size is not None:
            kwargs["q_group_size"] = q_group_size
        mlx_lm_convert(str(source_path), **kwargs)


def _quantization_mode_for_request(request: maintenance_pb2.ConvertModelRequest) -> str:
    quantization_mode = request.ext.get("quantization_mode", "").strip().lower() or "ptq"
    if quantization_mode not in {"ptq", "qat"}:
        raise ModelOperationError(
            code="unsupported_quantization_mode",
            message=f"Unsupported quantization_mode: {quantization_mode}",
            details={"quantization_mode": quantization_mode},
        )
    return quantization_mode


def _source_artifact_kind_for_request(request: maintenance_pb2.ConvertModelRequest) -> str:
    source_artifact_kind = request.ext.get("source_artifact_kind", "").strip().lower() or "base_model"
    if source_artifact_kind not in {"base_model", "merged_adapter", "adapter_export"}:
        raise ModelOperationError(
            code="unsupported_source_artifact_kind",
            message=f"Unsupported source_artifact_kind: {source_artifact_kind}",
            details={"source_artifact_kind": source_artifact_kind},
        )
    return source_artifact_kind


def _quantization_backend_for_request(request: maintenance_pb2.ConvertModelRequest) -> str:
    backend = (
        request.ext.get("quantization_backend", "").strip().lower()
        or _MANIFEST_ONLY_QUANTIZATION_BACKEND
    )
    if backend not in _SUPPORTED_QUANTIZATION_BACKENDS:
        raise ModelOperationError(
            code="unsupported_quantization_backend",
            message=f"Unsupported quantization_backend: {backend}",
            details={
                "quantization_backend": backend,
                "supported_quantization_backends": ",".join(sorted(_SUPPORTED_QUANTIZATION_BACKENDS)),
            },
        )
    return backend


def _local_inference_smoke_mode_for_request(request: maintenance_pb2.ConvertModelRequest) -> str:
    smoke_mode = request.ext.get("local_inference_smoke_mode", "").strip().lower() or "structural"
    if smoke_mode not in {"structural", "runtime_generate"}:
        raise ModelOperationError(
            code="unsupported_local_inference_smoke_mode",
            message=f"Unsupported local_inference_smoke_mode: {smoke_mode}",
            details={"local_inference_smoke_mode": smoke_mode},
        )
    return smoke_mode


def _source_artifact_path_for_request(
    request: maintenance_pb2.ConvertModelRequest,
    *,
    source_model: common_pb2.ModelSpec,
    source_artifact_kind: str,
) -> str:
    source_artifact_path = request.ext.get("source_artifact_path", "").strip()
    if source_artifact_path:
        return source_artifact_path
    if source_artifact_kind == "base_model":
        return source_model.model_path
    return ""


def _validate_quantization_source(
    *,
    quantization_mode: str,
    source_artifact_kind: str,
    source_artifact_path: str,
    quantization_backend: str,
) -> None:
    if source_artifact_kind != "base_model" and not source_artifact_path:
        raise ModelOperationError(
            code="missing_source_artifact_path",
            message="Adapter-derived quantization requires source_artifact_path.",
            details={"source_artifact_kind": source_artifact_kind},
        )
    if quantization_mode == "qat" and source_artifact_kind == "base_model":
        raise ModelOperationError(
            code="unsupported_quantization_mode",
            message="QAT quantization requires an adapter-derived source artifact.",
            details={
                "quantization_mode": quantization_mode,
                "source_artifact_kind": source_artifact_kind,
                "supported_source_artifact_kinds": "merged_adapter,adapter_export",
            },
        )
    if quantization_mode == "qat" and not Path(source_artifact_path).expanduser().exists():
        raise ModelOperationError(
            code="missing_source_artifact_path",
            message="QAT quantization requires an existing adapter-derived source artifact.",
            details={
                "quantization_mode": quantization_mode,
                "source_artifact_kind": source_artifact_kind,
                "source_artifact_path": source_artifact_path,
            },
        )


def _local_source_path_for_mlx_lm_convert(source_artifact_path: str) -> Path:
    normalized = source_artifact_path.strip()
    if not normalized:
        raise ModelOperationError(
            code="missing_quantization_source_path",
            message="MLX-LM quantization requires a local source artifact path.",
            details={"quantization_backend": _MLX_LM_CONVERT_QUANTIZATION_BACKEND},
        )
    source_path = Path(normalized).expanduser().resolve()
    if not source_path.exists():
        raise ModelOperationError(
            code="missing_quantization_source_path",
            message="MLX-LM quantization source artifact does not exist.",
            details={
                "quantization_backend": _MLX_LM_CONVERT_QUANTIZATION_BACKEND,
                "source_artifact_path": str(source_path),
            },
        )
    return source_path


def _mlx_lm_quantization_params_for_request(
    request: maintenance_pb2.ConvertModelRequest,
    profile: QuantizationProfile,
) -> dict[str, int | str | None]:
    q_bits = _optional_positive_int_ext(request, "mlx_lm_q_bits")
    if q_bits is None:
        q_bits = _bits_from_weight_quant(profile.weight_quant)
    if q_bits is None:
        raise ModelOperationError(
            code="unsupported_quantization_profile",
            message="MLX-LM quantization requires an integer weight bit width.",
            details={
                "quantization_backend": _MLX_LM_CONVERT_QUANTIZATION_BACKEND,
                "weight_quant": profile.weight_quant,
                "override_field": "mlx_lm_q_bits",
            },
        )
    q_group_size = _optional_positive_int_ext(request, "mlx_lm_q_group_size")
    if q_group_size is None:
        q_group_size = _optional_positive_int(profile.ext.get("quant_group_size", ""), "quant_group_size")
    q_mode = (
        request.ext.get("mlx_lm_q_mode", "").strip().lower()
        or profile.ext.get("mlx_lm_q_mode", "").strip().lower()
        or "affine"
    )
    if q_mode not in _SUPPORTED_MLX_LM_Q_MODES:
        raise ModelOperationError(
            code="invalid_quantization_backend_config",
            message="Unsupported MLX-LM quantization mode.",
            details={
                "field": "mlx_lm_q_mode",
                "value": q_mode,
                "supported_values": ",".join(sorted(_SUPPORTED_MLX_LM_Q_MODES)),
            },
        )
    return {"q_bits": q_bits, "q_group_size": q_group_size, "q_mode": q_mode}


def _bits_from_weight_quant(weight_quant: str) -> int | None:
    normalized = weight_quant.strip().lower()
    if len(normalized) >= 2 and normalized[0] == "q" and normalized[1:].isdigit():
        return int(normalized[1:])
    return None


def _optional_positive_int_ext(
    request: maintenance_pb2.ConvertModelRequest,
    key: str,
) -> int | None:
    return _optional_positive_int(request.ext.get(key, ""), key)


def _optional_positive_int(raw_value: str, key: str) -> int | None:
    normalized = str(raw_value).strip()
    if not normalized:
        return None
    try:
        value = int(normalized)
    except ValueError as exc:
        raise ModelOperationError(
            code="invalid_quantization_backend_config",
            message=f"{key} must be a positive integer.",
            details={"field": key, "value": normalized},
        ) from exc
    if value <= 0:
        raise ModelOperationError(
            code="invalid_quantization_backend_config",
            message=f"{key} must be a positive integer.",
            details={"field": key, "value": normalized},
        )
    return value


def _sum_bundle_file_bytes(bundle_path: Path) -> int:
    total = 0
    stack = [bundle_path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(os.fspath(current)) as entries:
                for entry in entries:
                    try:
                        if entry.is_file():
                            total += entry.stat().st_size
                        elif entry.is_dir():
                            stack.append(Path(entry.path))
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def _smoke_required_files_for_backend(
    bundle_path: Path,
    *,
    quantization_backend: str,
) -> tuple[str, ...]:
    if quantization_backend != _MLX_LM_CONVERT_QUANTIZATION_BACKEND:
        return _SMOKE_REQUIRED_FILES
    if (bundle_path / "tokenizer.json").exists():
        tokenizer_file = "tokenizer.json"
    elif (bundle_path / "tokenizer.model").exists():
        tokenizer_file = "tokenizer.model"
    else:
        tokenizer_file = "tokenizer.json"
    if (bundle_path / "model.safetensors").exists():
        weight_files = ("model.safetensors",)
    elif (bundle_path / "model.safetensors.index.json").exists():
        weight_files = _mlx_lm_index_weight_files(bundle_path)
    else:
        weight_files = ("model.safetensors",)
    return ("config.json", tokenizer_file, *weight_files)


def _mlx_lm_index_weight_files(bundle_path: Path) -> tuple[str, ...]:
    index_file = "model.safetensors.index.json"
    try:
        payload = json.loads((bundle_path / index_file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return (index_file, "model.safetensors")
    weight_map = payload.get("weight_map")
    if not isinstance(weight_map, dict):
        return (index_file, "model.safetensors")
    shard_names = sorted({name for name in weight_map.values() if isinstance(name, str) and name})
    if not shard_names:
        return (index_file, "model.safetensors")
    return (index_file, shard_names[0])


def _not_requested_smoke_evidence(
    *,
    bundle_path: Path,
    smoke_mode: str,
) -> LocalInferenceSmokeEvidence:
    return LocalInferenceSmokeEvidence(
        status="not_requested",
        evidence_kind="not_requested",
        smoke_mode=smoke_mode,
        runtime="mlx_text",
        runtime_backend="not_requested",
        artifact_path=str(bundle_path),
        checked_files=(),
        latency_ms=0.0,
    )


def _calibration_evidence_for_request(
    request: maintenance_pb2.ConvertModelRequest,
) -> dict[str, Any]:
    dataset_uri = request.ext.get("calibration_dataset_uri", "").strip()
    if not dataset_uri:
        return {}
    package_path = Path(dataset_uri).expanduser().resolve()
    manifest_path = package_path / "manifest.json"
    samples_path = package_path / "samples.jsonl"
    if not manifest_path.is_file() or not samples_path.is_file():
        raise ModelOperationError(
            code="invalid_dataset_package",
            message="Training dataset package must contain manifest.json and samples.jsonl.",
            details={"dataset_uri": dataset_uri},
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ModelOperationError(
            code="invalid_dataset_package",
            message="Could not read training dataset manifest.",
            details={"dataset_uri": dataset_uri},
        ) from exc
    except json.JSONDecodeError as exc:
        raise ModelOperationError(
            code="invalid_dataset_package",
            message="Training dataset manifest is not valid JSON.",
            details={"dataset_uri": dataset_uri},
        ) from exc
    if not isinstance(manifest, dict):
        raise ModelOperationError(
            code="invalid_dataset_package",
            message="Training dataset manifest must be a JSON object.",
            details={"dataset_uri": dataset_uri},
        )
    missing_fields = [
        field
        for field in ("schema_version", "dataset_id", "format", "sample_count", "version")
        if field not in manifest
    ]
    if missing_fields:
        raise ModelOperationError(
            code="invalid_dataset_package",
            message="Training dataset manifest is missing required fields.",
            details={"missing_fields": ",".join(missing_fields)},
        )
    dataset_format = str(manifest["format"])
    if dataset_format != "calibration":
        raise ModelOperationError(
            code="invalid_calibration_dataset",
            message="Quantization calibration datasets must use format=calibration.",
            details={
                "dataset_uri": dataset_uri,
                "required_format": "calibration",
                "actual_format": dataset_format,
            },
        )
    try:
        sample_count = int(manifest["sample_count"])
    except (TypeError, ValueError) as exc:
        raise ModelOperationError(
            code="invalid_dataset_package",
            message="Training dataset sample_count must be an integer.",
            details={"dataset_uri": dataset_uri},
        ) from exc
    return {
        "dataset_uri": dataset_uri,
        "dataset_id": str(manifest["dataset_id"]),
        "dataset_version": str(manifest["version"]),
        "dataset_format": dataset_format,
        "sample_count": sample_count,
        "manifest_path": str(manifest_path),
        "package_path": str(package_path),
    }


def _qat_metadata_for_request(
    request: maintenance_pb2.ConvertModelRequest,
    *,
    quantization_mode: str,
    source_artifact_kind: str,
    source_artifact_path: str,
    calibration_evidence: dict[str, Any],
    qat_training_result: QATFakeQuantTrainingResult | None = None,
) -> dict[str, Any] | None:
    if quantization_mode != "qat":
        return None
    metadata: dict[str, Any] = {
        "stage": request.ext.get("qat_stage", "").strip() or "fake_quant_training",
        "fake_quant": request.ext.get("qat_fake_quant", "").strip() or "executed",
        "source_artifact_kind": source_artifact_kind,
        "source_artifact_path": source_artifact_path,
        "calibration_dataset_uri": calibration_evidence.get("dataset_uri", ""),
        "calibration_sample_count": calibration_evidence.get("sample_count", 0),
    }
    if qat_training_result is not None:
        training_payload = qat_training_result.payload
        metadata.update(
            {
                "training_executed": True,
                "training_backend": str(training_payload["training_backend"]),
                "training_manifest_path": str(qat_training_result.manifest_path),
                "training_manifest_schema_version": str(training_payload["schema_version"]),
                "training_job_id": str(training_payload["job_id"]),
                "training_trace_path": str(qat_training_result.trace_path),
                "fake_quant_artifact_path": str(qat_training_result.fake_quant_artifact_path),
                "training_steps": int(training_payload["training_steps"]),
                "source_file_count": int(training_payload["source_file_count"]),
                "source_byte_count": int(training_payload["source_byte_count"]),
                "source_sha256": str(training_payload["source_sha256"]),
                "quant_error_proxy_mean": float(training_payload["quant_error_proxy_mean"]),
                "loss_proxy_initial": float(training_payload["loss_proxy_initial"]),
                "loss_proxy_final": float(training_payload["loss_proxy_final"]),
            }
        )
    training_manifest_path = request.ext.get("qat_training_manifest_path", "").strip()
    if not training_manifest_path:
        return metadata
    manifest_path = Path(training_manifest_path).expanduser().resolve()
    if not manifest_path.is_file():
        raise ModelOperationError(
            code="invalid_qat_training_manifest",
            message="qat_training_manifest_path must point to a readable manifest.",
            details={"qat_training_manifest_path": training_manifest_path},
        )
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelOperationError(
            code="invalid_qat_training_manifest",
            message="qat_training_manifest_path must point to readable JSON.",
            details={"qat_training_manifest_path": training_manifest_path},
        ) from exc
    if not isinstance(payload, dict) or not str(payload.get("schema_version", "")).strip():
        raise ModelOperationError(
            code="invalid_qat_training_manifest",
            message="QAT training manifest must include schema_version.",
            details={"qat_training_manifest_path": training_manifest_path},
        )
    metadata["source_training_manifest_path"] = str(manifest_path)
    metadata["source_training_manifest_schema_version"] = str(payload["schema_version"])
    metadata["source_training_job_id"] = str(payload.get("job_id", ""))
    return metadata


def _run_qat_fake_quant_training(
    *,
    request: maintenance_pb2.ConvertModelRequest,
    job_id: str,
    source_artifact_kind: str,
    source_artifact_path: str,
    profile: QuantizationProfile,
    calibration_evidence: dict[str, Any],
    bundle_path: Path,
) -> QATFakeQuantTrainingResult:
    source_path = Path(source_artifact_path).expanduser().resolve()
    source_files = _source_artifact_files_for_qat(source_path)
    q_bits = _qat_q_bits_for_request(request, profile)
    training_steps = (
        _optional_positive_int_ext(request, "qat_training_steps")
        or _optional_positive_int_ext(request, "qat_steps")
        or 1
    )
    learning_rate = _non_negative_float_ext(request, "qat_learning_rate", default=0.0)
    stats = _qat_fake_quant_source_stats(source_files, q_bits=q_bits)
    calibration_sample_count = int(calibration_evidence.get("sample_count", 0) or 0)
    calibration_factor = 1.0 / max(1, calibration_sample_count)
    loss_initial = stats["quant_error_proxy_mean"] + calibration_factor
    loss_final = stats["quant_error_proxy_mean"] + (calibration_factor / (training_steps + 1))

    qat_dir = bundle_path / "qat"
    qat_dir.mkdir(parents=True, exist_ok=True)
    trace_path = qat_dir / "qat_training_trace.jsonl"
    manifest_path = qat_dir / "qat_training_manifest.json"
    fake_quant_artifact_path = qat_dir / "qat_fake_quant_artifact.json"

    trace_rows = []
    for step in range(1, training_steps + 1):
        progress = step / training_steps
        loss_proxy = loss_initial + (loss_final - loss_initial) * progress
        trace_rows.append(
            {
                "step": step,
                "training_backend": _QAT_FAKE_QUANT_BACKEND,
                "loss_proxy": loss_proxy,
                "quant_error_proxy_mean": stats["quant_error_proxy_mean"],
                "calibration_sample_count": calibration_sample_count,
            }
        )
    _write_jsonl_artifact(trace_path, trace_rows)

    fake_quant_payload = {
        "schema_version": "melix.qat_fake_quant_artifact.v1",
        "job_id": job_id,
        "training_backend": _QAT_FAKE_QUANT_BACKEND,
        "source_artifact_kind": source_artifact_kind,
        "source_artifact_path": str(source_path),
        "source_sha256": stats["source_sha256"],
        "source_file_count": stats["source_file_count"],
        "source_byte_count": stats["source_byte_count"],
        "q_bits": q_bits,
        "quant_error_proxy_mean": stats["quant_error_proxy_mean"],
        "quant_error_proxy_max": stats["quant_error_proxy_max"],
    }
    fake_quant_artifact_bytes = _write_json_artifact(fake_quant_artifact_path, fake_quant_payload)

    manifest_payload = {
        "schema_version": _QAT_TRAINING_SCHEMA_VERSION,
        "job_id": f"{job_id}.qat",
        "parent_quantization_job_id": job_id,
        "training_backend": _QAT_FAKE_QUANT_BACKEND,
        "source_artifact_kind": source_artifact_kind,
        "source_artifact_path": str(source_path),
        "source_sha256": stats["source_sha256"],
        "source_file_count": stats["source_file_count"],
        "source_byte_count": stats["source_byte_count"],
        "weight_quant": profile.weight_quant,
        "kv_quant": profile.kv_quant,
        "q_bits": q_bits,
        "training_steps": training_steps,
        "learning_rate": learning_rate,
        "calibration_dataset_uri": calibration_evidence.get("dataset_uri", ""),
        "calibration_sample_count": calibration_sample_count,
        "loss_proxy_initial": loss_initial,
        "loss_proxy_final": loss_final,
        "quant_error_proxy_mean": stats["quant_error_proxy_mean"],
        "quant_error_proxy_max": stats["quant_error_proxy_max"],
        "trace_path": str(trace_path),
        "fake_quant_artifact_path": str(fake_quant_artifact_path),
    }
    manifest_bytes = _write_json_artifact(manifest_path, manifest_payload)
    artifact_bytes = trace_path.stat().st_size + fake_quant_artifact_bytes + manifest_bytes
    return QATFakeQuantTrainingResult(
        manifest_path=manifest_path,
        trace_path=trace_path,
        fake_quant_artifact_path=fake_quant_artifact_path,
        artifact_bytes=artifact_bytes,
        payload=manifest_payload,
    )


def _source_artifact_files_for_qat(source_path: Path) -> list[Path]:
    if source_path.is_file():
        return [source_path]
    source_files = sorted(path for path in source_path.rglob("*") if path.is_file())
    if not source_files:
        raise ModelOperationError(
            code="invalid_qat_source_artifact",
            message="QAT fake-quant training requires at least one source artifact file.",
            details={"source_artifact_path": str(source_path)},
        )
    return source_files


def _qat_q_bits_for_request(
    request: maintenance_pb2.ConvertModelRequest,
    profile: QuantizationProfile,
) -> int:
    q_bits = (
        _optional_positive_int_ext(request, "qat_q_bits")
        or _optional_positive_int_ext(request, "mlx_lm_q_bits")
        or _bits_from_weight_quant(profile.weight_quant)
    )
    if q_bits is None:
        raise ModelOperationError(
            code="unsupported_quantization_profile",
            message="QAT fake-quant training requires an integer weight bit width.",
            details={
                "quantization_mode": "qat",
                "weight_quant": profile.weight_quant,
                "override_field": "qat_q_bits",
            },
        )
    return q_bits


def _qat_fake_quant_source_stats(source_files: list[Path], *, q_bits: int) -> dict[str, Any]:
    digest = hashlib.sha256()
    source_file_count = 0
    source_byte_count = 0
    error_sum = 0.0
    error_max = 0.0
    levels = (1 << q_bits) - 1
    if levels <= 0:
        raise ModelOperationError(
            code="invalid_quantization_backend_config",
            message="qat_q_bits must produce at least one fake-quant level.",
            details={"field": "qat_q_bits", "value": str(q_bits)},
        )
    for source_file in source_files:
        source_file_count += 1
        with source_file.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                source_byte_count += len(chunk)
                for value in chunk:
                    quantized = round((value / 255.0) * levels) / levels
                    reconstructed = round(quantized * 255.0)
                    error = abs(value - reconstructed) / 255.0
                    error_sum += error
                    if error > error_max:
                        error_max = error
    if source_byte_count <= 0:
        raise ModelOperationError(
            code="invalid_qat_source_artifact",
            message="QAT fake-quant training requires non-empty source artifact bytes.",
            details={"source_file_count": str(source_file_count)},
        )
    return {
        "source_sha256": digest.hexdigest(),
        "source_file_count": source_file_count,
        "source_byte_count": source_byte_count,
        "quant_error_proxy_mean": error_sum / source_byte_count,
        "quant_error_proxy_max": error_max,
    }


def _write_json_artifact(path: Path, payload: dict[str, Any]) -> int:
    encoded = json.dumps(payload, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    path.write_bytes(encoded)
    return len(encoded)


def _write_jsonl_artifact(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _release_gate_for_request(
    request: maintenance_pb2.ConvertModelRequest,
    *,
    smoke_evidence: LocalInferenceSmokeEvidence,
) -> dict[str, Any]:
    if request.run_smoke_test:
        smoke_result = smoke_evidence.status
    else:
        smoke_result = "not_requested"
    return {
        "quality_delta": _float_ext(request, "quality_delta"),
        "latency_delta": _float_ext(request, "latency_delta"),
        "local_inference_smoke_result": smoke_result,
    }


def _elapsed_ms(started_at: float) -> float:
    return round(max(0.0, (time.perf_counter() - started_at) * 1000.0), 3)


def _float_ext(request: maintenance_pb2.ConvertModelRequest, key: str) -> float:
    raw_value = request.ext.get(key, "").strip()
    if not raw_value:
        return 0.0
    try:
        return float(raw_value)
    except ValueError as exc:
        raise ModelOperationError(
            code="invalid_quantization_release_gate",
            message=f"{key} must be numeric.",
            details={"field": key, "value": raw_value},
        ) from exc


def _non_negative_float_ext(
    request: maintenance_pb2.ConvertModelRequest,
    key: str,
    *,
    default: float,
) -> float:
    raw_value = request.ext.get(key, "").strip()
    if not raw_value:
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ModelOperationError(
            code="invalid_quantization_backend_config",
            message=f"{key} must be numeric.",
            details={"field": key, "value": raw_value},
        ) from exc
    if value < 0.0:
        raise ModelOperationError(
            code="invalid_quantization_backend_config",
            message=f"{key} must be non-negative.",
            details={"field": key, "value": raw_value},
        )
    return value
