from __future__ import annotations

import hashlib
import json
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
_SMOKE_REQUIRED_FILES = ("config.json", "tokenizer.json", "weights.safetensors")
_MANIFEST_ONLY_QUANTIZATION_BACKEND = "manifest_only"
_MLX_LM_CONVERT_QUANTIZATION_BACKEND = "mlx_lm_convert"
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
        if quantization_backend == _MLX_LM_CONVERT_QUANTIZATION_BACKEND:
            artifact_bytes = self._write_mlx_lm_quantized_bundle(
                request=request,
                source_artifact_path=source_artifact_path,
                profile=profile,
                bundle_path=bundle_path,
            )
        else:
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
            artifact_bytes = 0
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
                    },
                    sort_keys=True,
                ).encode("utf-8"),
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
        if quantization_mode == "qat":
            payload["qat"] = {
                "fake_quant": request.ext.get("qat_fake_quant", "").strip() or "recorded",
            }
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
        try:
            self._mlx_lm_convert(
                source_path=source_path,
                output_path=bundle_path,
                q_group_size=params["q_group_size"],
                q_bits=params["q_bits"],
                q_mode=params["q_mode"],
            )
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
        q_group_size: int | None,
        q_bits: int,
        q_mode: str,
    ) -> None:
        from mlx_lm import convert as mlx_lm_convert

        mlx_lm_convert(
            str(source_path),
            mlx_path=str(output_path),
            quantize=True,
            q_group_size=q_group_size,
            q_bits=q_bits,
            q_mode=q_mode,
        )


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
    if (
        quantization_backend == _MLX_LM_CONVERT_QUANTIZATION_BACKEND
        and quantization_mode != "ptq"
    ):
        raise ModelOperationError(
            code="unsupported_quantization_backend",
            message="MLX-LM conversion backend supports PTQ only.",
            details={
                "quantization_backend": quantization_backend,
                "quantization_mode": quantization_mode,
                "supported_quantization_mode": "ptq",
            },
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
    return sum(path.stat().st_size for path in bundle_path.rglob("*") if path.is_file())


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
        weight_file = "model.safetensors"
    elif (bundle_path / "model.safetensors.index.json").exists():
        weight_file = "model.safetensors.index.json"
    else:
        weight_file = "model.safetensors"
    return ("config.json", tokenizer_file, weight_file)


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
