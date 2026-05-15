from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
import logging
import math
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
from threading import Event
import time
from typing import Any, Iterator, NoReturn

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, maintenance_pb2

from worker.dataset_registry.catalog import DatasetCatalog
from worker.model_ops.adapter_activation_pipeline import AdapterActivationPipeline
from worker.model_ops.conversion_pipeline import ModelConversionPipeline
from worker.model_ops.download_pipeline import DownloadPipeline
from worker.model_ops.errors import ModelOperationError
from worker.model_ops.hub_catalog import (
    HubCatalog,
    HubCatalogError,
    HubModelCardRecord,
    HubModelSummaryRecord,
)
from worker.model_ops.job_registry import ModelOpsJobRegistry
from worker.model_ops.lora_training_pipeline import LoRATrainingPipeline
from worker.model_ops.local_import_pipeline import LocalImportPipeline
from worker.model_ops.operation_locks import ModelOpsConflictRegistry
from worker.model_ops.quantization_pipeline import OQQuantizationPipeline
from worker.model_ops.quantization_profiles import protected_scope_for_request
from worker.model_ops.training_dataset import build_training_dataset_artifact
from worker.model_ops.upload_receipt_pipeline import UploadReceiptPipeline
from worker.productization.benchmark_queue import BenchmarkQueueRecord, BenchmarkQueueStore
from worker.productization.benchmark_suites import BenchmarkSuiteCatalog, ResolvedBenchmarkSuite
from worker.productization.synthetic_dataset_generation import (
    SyntheticColumnSpec,
    SyntheticDatasetRequest,
    SyntheticModelConfig,
    SyntheticModelProvider,
    SyntheticSeedSource,
    generate_synthetic_dataset_package,
)
from worker.registry import WorkerRegistry
from worker.runtime.agentic_tools import execute_agentic_tool_calls
from worker.runtime.multimodal_preprocessing import PreparedVisionRequest

_CAPABILITY_SUPPORTED_MODALITIES_KEY = "melix.capability.supported_modalities"
_CAPABILITY_SUPPORTED_TASKS_KEY = "melix.capability.supported_tasks"
_CAPABILITY_SUPPORTED_PARSERS_KEY = "melix.capability.supported_parsers"

logger = logging.getLogger(__name__)


class ShapedBenchmarkPrompt(str):
    __slots__ = ("_tokens",)

    def __new__(cls, value: str, tokens: tuple[str, ...]) -> ShapedBenchmarkPrompt:
        prompt = str.__new__(cls, value)
        prompt._tokens = tokens
        return prompt

    def split(self, sep: str | None = None, maxsplit: int = -1) -> list[str]:
        if sep is None and maxsplit == -1:
            return list(self._tokens)
        return str(self).split(sep, maxsplit)

    @property
    def tokens(self) -> tuple[str, ...]:
        return self._tokens

    @property
    def token_count(self) -> int:
        return len(self._tokens)


@dataclass(frozen=True)
class BenchMetricSpec:
    suite: str
    name: str
    value: float
    unit: str


@dataclass(frozen=True)
class BenchSample:
    ttft_ms: float
    total_latency_ms: float
    completion_tokens: int
    prompt_tokens: int = 0
    request_latency_ms: float = 0.0
    prefill_tokens_per_second: float = 0.0
    decode_tokens_per_second: float = 0.0
    peak_memory_bytes: float = 0.0
    image_feature_cache_hits: int = 0
    image_feature_cache_misses: int = 0
    multimodal_decode_mode: str = "baseline"
    multimodal_fallback_reason: str = "not_reported"
    multimodal_decode_sync_mode: str = "baseline"
    multi_image_scatter_mode: str = "none"
    quantized_load_mode: str = "fallback"
    quantized_load_fallback_reason: str = "not_reported"
    dataset_materialize_ms: float = 0.0
    prompt_render_ms: float = 0.0
    warmup_ms: float = 0.0
    prefill_ms: float = 0.0
    decode_ms: float = 0.0
    first_token_index: int = 0
    cache_hit: bool = False
    runtime_kind: str = ""
    error_stage: str = ""
    speculative_acceptance_rate: float = 0.0
    speculative_rollback_rate: float = 0.0
    speculative_accepted_tokens: int = 0
    speculative_rejected_tokens: int = 0
    speculative_fallback_count: int = 0
    speculative_num_draft_tokens: int = 0
    speculative_draft_model_configured: bool = False
    speculative_draft_propose_ms: float = 0.0
    speculative_target_verify_ms: float = 0.0
    dflash_enabled: bool = False
    dflash_block_size: int = 0
    dflash_rollback_count: int = 0
    dflash_target_hidden_layers: int = 0


_BENCHMARK_ERROR_STAGES = {
    "dataset_materialize",
    "prompt_render",
    "warmup",
    "prefill",
    "decode",
    "runtime",
    "validation",
}


@dataclass(frozen=True)
class ImageBenchSample:
    latency_ms: float
    artifact_publish_ms: float
    output_bytes: int


@dataclass(frozen=True)
class ModelOperationManifestResult:
    manifest: dict[str, Any]
    manifest_path: Path
    output_path: Path | None = None


@dataclass(frozen=True)
class BenchmarkLoadedModelResolution:
    lazy_model_handle: str
    loaded_model: Any
    load_rss_before_bytes: int
    load_rss_after_bytes: int

    @property
    def load_triggered_by_run(self) -> bool:
        return bool(self.lazy_model_handle)

    def __iter__(self):
        yield self.lazy_model_handle
        yield self.loaded_model


def _split_capability_values(raw_value: str) -> list[str]:
    return [
        part.strip()
        for part in raw_value.split(",")
        if part.strip()
    ]


def _default_capability_lists(model_kind: str) -> tuple[list[str], list[str]]:
    if model_kind == "ocr":
        return ["text", "image"], ["ocr", "generate"]
    if model_kind == "vlm":
        return ["text", "image"], ["vlm", "generate"]
    if model_kind == "transcription":
        return ["audio", "text"], ["transcribe"]
    if model_kind == "speech":
        return ["text", "audio"], ["speak"]
    if model_kind == "image":
        return ["text", "image"], ["image_generate", "image_edit"]
    return ["text"], ["generate"]


def _model_backend_id(model: common_pb2.ModelSpec) -> str:
    ext = model.ext
    return (
        ext.get("text_backend_id", "")
        or ext.get("embedding_backend_id", "")
        or ext.get("rerank_backend_id", "")
        or ext.get("melix.vlm.backend_id", "")
        or ext.get("melix.image.backend_id", "")
        or ext.get("melix.audio.backend_id", "")
    )


def _model_family_id(model: common_pb2.ModelSpec) -> str:
    ext = model.ext
    return (
        ext.get("text_family_id", "")
        or ext.get("embedding_family_id", "")
        or ext.get("rerank_family_id", "")
        or ext.get("vision_family_id", "")
        or ext.get("melix.image.family_id", "")
        or ext.get("melix.audio.family_id", "")
        or ext.get("detected_family_id", "")
    )


def _health_status_rank(status: maintenance_pb2.HealthStatus) -> int:
    if status == maintenance_pb2.HEALTH_STATUS_FAILED:
        return 4
    if status == maintenance_pb2.HEALTH_STATUS_DEGRADED:
        return 3
    if status == maintenance_pb2.HEALTH_STATUS_WARNING:
        return 2
    if status == maintenance_pb2.HEALTH_STATUS_HEALTHY:
        return 1
    return 0


def _registry_rescan_enabled(ext: dict[str, str]) -> bool:
    return ext.get("melix.registry_rescan", "").strip().lower() in {"1", "true", "yes", "on"}


def _registry_roots_override(ext: dict[str, str]) -> list[str] | None:
    raw_json = ext.get("melix.registry_roots_json", "").strip()
    if raw_json:
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, list):
            roots = [str(item).strip() for item in payload if str(item).strip()]
            return roots

    raw_legacy = ext.get("melix.registry_roots", "").strip()
    if raw_legacy:
        roots = [part.strip() for part in raw_legacy.split(os.pathsep) if part.strip()]
        return roots

    return None


def _write_jsonl_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _synthetic_dataset_request_from_ext(
    ext: dict[str, str],
    *,
    job_id: str,
) -> SyntheticDatasetRequest:
    columns = _synthetic_columns_from_ext(ext)
    seed_source = _synthetic_seed_source_from_ext(ext)
    return SyntheticDatasetRequest(
        dataset_id=_required_ext(ext, "synthetic_dataset_id"),
        dataset_name=_required_ext(ext, "synthetic_dataset_name"),
        mode=ext.get("synthetic_mode", "").strip() or "create",
        num_records=_positive_int_ext(ext, "synthetic_num_records"),
        output_kind=_required_ext(ext, "synthetic_output_kind"),
        output_format=_required_ext(ext, "synthetic_output_format"),
        model_provider=SyntheticModelProvider(
            endpoint=_required_ext(ext, "provider_endpoint"),
            name=ext.get("provider_name", "").strip() or "melix",
            provider_type=ext.get("provider_type", "").strip() or "openai",
            api_key=ext.get("api_key", "").strip(),
            extra_headers=_synthetic_headers_from_ext(ext),
        ),
        models=(
            SyntheticModelConfig(
                alias=ext.get("model_alias", "").strip() or "generator",
                model=_required_ext(ext, "model"),
                temperature=_optional_float_ext(ext, "temperature"),
                top_p=_optional_float_ext(ext, "top_p"),
                max_tokens=_optional_positive_int_ext(ext, "max_tokens"),
                timeout_seconds=_optional_float_ext(ext, "timeout_seconds"),
                max_parallel_requests=_optional_positive_int_ext(ext, "max_parallel_requests"),
                extra_body=_json_object_ext(ext, "extra_body_json", default={}),
            ),
        ),
        columns=columns,
        job_id=job_id,
        seed_source=seed_source,
        validation_ratio=_optional_float_ext(ext, "validation_ratio") or 0.0,
        preview_count=_optional_positive_int_ext(ext, "preview_count") or 3,
        random_seed=_optional_int_ext(ext, "random_seed"),
        data_designer_resume_mode=ext.get("resume", "").strip() or "never",
        disable_data_designer_telemetry=_boolean_ext(ext, "disable_datadesigner_telemetry", default=True),
    )


def _required_ext(ext: dict[str, str], key: str) -> str:
    value = ext.get(key, "").strip()
    if not value:
        raise ModelOperationError(
            code="invalid_synthetic_dataset_request",
            message=f"{key} is required for synthetic dataset generation.",
            details={"field": key},
        )
    return value


def _positive_int_ext(ext: dict[str, str], key: str) -> int:
    value = _optional_positive_int_ext(ext, key)
    if value is None:
        raise ModelOperationError(
            code="invalid_synthetic_dataset_request",
            message=f"{key} must be greater than zero.",
            details={"field": key},
        )
    return value


def _optional_positive_int_ext(ext: dict[str, str], key: str) -> int | None:
    raw_value = ext.get(key, "").strip()
    if not raw_value:
        return None
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ModelOperationError(
            code="invalid_synthetic_dataset_request",
            message=f"{key} must be an integer.",
            details={"field": key, "value": raw_value},
        ) from exc
    if value <= 0:
        raise ModelOperationError(
            code="invalid_synthetic_dataset_request",
            message=f"{key} must be greater than zero.",
            details={"field": key, "value": raw_value},
        )
    return value


def _optional_int_ext(ext: dict[str, str], key: str) -> int | None:
    raw_value = ext.get(key, "").strip()
    if not raw_value:
        return None
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ModelOperationError(
            code="invalid_synthetic_dataset_request",
            message=f"{key} must be an integer.",
            details={"field": key, "value": raw_value},
        ) from exc


def _optional_float_ext(ext: dict[str, str], key: str) -> float | None:
    raw_value = ext.get(key, "").strip()
    if not raw_value:
        return None
    try:
        return float(raw_value)
    except ValueError as exc:
        raise ModelOperationError(
            code="invalid_synthetic_dataset_request",
            message=f"{key} must be numeric.",
            details={"field": key, "value": raw_value},
        ) from exc


def _boolean_ext(ext: dict[str, str], key: str, *, default: bool) -> bool:
    raw_value = ext.get(key, "").strip().lower()
    if not raw_value:
        return default
    if raw_value in {"1", "true", "yes", "on"}:
        return True
    if raw_value in {"0", "false", "no", "off"}:
        return False
    raise ModelOperationError(
        code="invalid_synthetic_dataset_request",
        message=f"{key} must be a boolean.",
        details={"field": key, "value": raw_value},
    )


def _json_object_ext(ext: dict[str, str], key: str, *, default: dict[str, Any]) -> dict[str, Any]:
    raw_value = ext.get(key, "").strip()
    if not raw_value:
        return default
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ModelOperationError(
            code="invalid_synthetic_dataset_request",
            message=f"{key} must be valid JSON.",
            details={"field": key},
        ) from exc
    if not isinstance(payload, dict):
        raise ModelOperationError(
            code="invalid_synthetic_dataset_request",
            message=f"{key} must be a JSON object.",
            details={"field": key},
        )
    return payload


def _json_string_list_ext(ext: dict[str, str], key: str) -> list[str]:
    raw_value = ext.get(key, "").strip()
    if not raw_value:
        return []
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ModelOperationError(
            code="invalid_synthetic_dataset_request",
            message=f"{key} must be valid JSON.",
            details={"field": key},
        ) from exc
    if not isinstance(payload, list):
        raise ModelOperationError(
            code="invalid_synthetic_dataset_request",
            message=f"{key} must be a JSON array.",
            details={"field": key},
        )
    return [str(item) for item in payload]


def _synthetic_headers_from_ext(ext: dict[str, str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for raw_header in _json_string_list_ext(ext, "headers_json"):
        key, separator, value = raw_header.partition("=")
        key = key.strip()
        if not separator or not key:
            raise ModelOperationError(
                code="invalid_synthetic_dataset_request",
                message="Synthetic provider headers must use KEY=VALUE syntax.",
                details={"header": raw_header},
            )
        headers[key] = value
    return headers


def _synthetic_columns_from_ext(ext: dict[str, str]) -> tuple[SyntheticColumnSpec, ...]:
    columns: list[SyntheticColumnSpec] = []
    for raw_column in _json_string_list_ext(ext, "columns_json"):
        parts = raw_column.split(":", 2)
        if len(parts) != 3 or not parts[0].strip() or not parts[1].strip():
            raise ModelOperationError(
                code="invalid_synthetic_dataset_request",
                message="Synthetic columns must use NAME:TYPE:JSON_OR_PATH syntax.",
                details={"column": raw_column},
            )
        name, column_type, raw_params = parts[0].strip(), parts[1].strip(), parts[2].strip()
        columns.append(
            SyntheticColumnSpec(
                name=name,
                column_type=column_type,
                params=_synthetic_column_params(column_type, raw_params),
            )
        )
    if not columns:
        raise ModelOperationError(
            code="invalid_synthetic_dataset_request",
            message="At least one synthetic column is required.",
        )
    return tuple(columns)


def _synthetic_column_params(column_type: str, raw_params: str) -> dict[str, Any]:
    if not raw_params:
        return {}
    if raw_params.startswith(("{", "[")):
        try:
            payload = json.loads(raw_params)
        except json.JSONDecodeError as exc:
            raise ModelOperationError(
                code="invalid_synthetic_dataset_request",
                message="Synthetic column JSON parameters must be valid JSON.",
                details={"column_type": column_type},
            ) from exc
        if not isinstance(payload, dict):
            raise ModelOperationError(
                code="invalid_synthetic_dataset_request",
                message="Synthetic column JSON parameters must be an object.",
                details={"column_type": column_type},
            )
        return payload
    value = _synthetic_column_payload_value(raw_params)
    if column_type in {"llm_text", "llm_structured", "llm_judge"}:
        return {"prompt": value}
    if column_type == "expression":
        return {"expression": value}
    if column_type == "sampler":
        return {"values": value}
    return {"value": value}


def _synthetic_column_payload_value(raw_params: str) -> str:
    if not raw_params.startswith("@"):
        return raw_params
    candidate = raw_params[1:]
    if not candidate:
        return raw_params
    path = Path(candidate).expanduser()
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return raw_params


def _synthetic_seed_source_from_ext(ext: dict[str, str]) -> SyntheticSeedSource | None:
    source_kind = ext.get("seed_source_kind", "").strip()
    source_path = ext.get("seed_source_path", "").strip()
    if not source_kind and not source_path:
        return None
    if not source_kind or not source_path:
        raise ModelOperationError(
            code="invalid_synthetic_dataset_request",
            message="seed_source_kind and seed_source_path must be provided together.",
        )
    return SyntheticSeedSource(source_kind=source_kind, source_path=Path(source_path))


class MaintenanceCore:
    def __init__(
        self,
        registry: WorkerRegistry,
        jobs_root: Path,
        job_registry: ModelOpsJobRegistry | None = None,
        hub_catalog: HubCatalog | None = None,
        download_pipeline: DownloadPipeline | None = None,
        local_import_pipeline: LocalImportPipeline | None = None,
        lora_training_pipeline: LoRATrainingPipeline | None = None,
        adapter_activation_pipeline: AdapterActivationPipeline | None = None,
        upload_receipt_pipeline: UploadReceiptPipeline | None = None,
        benchmark_suite_catalog: BenchmarkSuiteCatalog | None = None,
        dataset_catalog: DatasetCatalog | None = None,
    ) -> None:
        self._registry = registry
        self._jobs_root = Path(jobs_root)
        self._job_registry = job_registry or ModelOpsJobRegistry(self._jobs_root)
        self._hub_catalog = hub_catalog or HubCatalog()
        self._conversion_pipeline = ModelConversionPipeline(registry)
        self._quantization_pipeline = OQQuantizationPipeline(registry)
        self._download_pipeline = download_pipeline or DownloadPipeline()
        self._local_import_pipeline = local_import_pipeline or LocalImportPipeline()
        self._lora_training_pipeline = lora_training_pipeline or LoRATrainingPipeline(
            policy_runtime=registry.runtime,
            reward_runtime=registry.runtime,
        )
        self._adapter_activation_pipeline = adapter_activation_pipeline or AdapterActivationPipeline()
        self._upload_receipt_pipeline = upload_receipt_pipeline or UploadReceiptPipeline()
        self._operation_locks = ModelOpsConflictRegistry()
        self._benchmark_store = None
        self._benchmark_queue_store = BenchmarkQueueStore()
        self._benchmark_suite_catalog = benchmark_suite_catalog or BenchmarkSuiteCatalog()
        self._dataset_catalog = dataset_catalog or DatasetCatalog()
        self._restore_derived_models_into_catalog()

    @staticmethod
    def _worker_quant_profile(profile) -> maintenance_pb2.QuantizationProfile:
        message = maintenance_pb2.QuantizationProfile(
            algorithm=profile.algorithm,
            schema_version=profile.schema_version,
            quant_profile_id=profile.quant_profile_id,
            weight_quant=profile.weight_quant,
            kv_quant=profile.kv_quant,
        )
        if profile.ext:
            message.ext.update(profile.ext)
        return message

    @staticmethod
    def _worker_artifact(
        *,
        schema_version: str,
        artifact_kind: str,
        bundle_path: Path,
        manifest_path: Path,
        artifact_bytes: int,
        manifest_bytes: int,
        serving_compatible: bool,
        smoke_test_requested: bool,
        smoke_test_passed: bool,
        runtime: str,
    ) -> maintenance_pb2.QuantizedArtifact:
        return maintenance_pb2.QuantizedArtifact(
            schema_version=schema_version,
            artifact_kind=artifact_kind,
            manifest_path=str(manifest_path),
            bundle_path=str(bundle_path),
            artifact_bytes=artifact_bytes,
            manifest_bytes=manifest_bytes,
            serving_compatible=serving_compatible,
            smoke_test_requested=smoke_test_requested,
            smoke_test_passed=smoke_test_passed,
            runtime=runtime,
        )

    @staticmethod
    def _hub_summary_message(record: HubModelSummaryRecord) -> maintenance_pb2.HubModelSummary:
        return maintenance_pb2.HubModelSummary(
            repo_id=record.repo_id,
            author=record.author,
            model_name=record.model_name,
            summary=record.summary,
            pipeline_tag=record.pipeline_tag,
            tags=record.tags,
            downloads=record.downloads,
            likes=record.likes,
            mlx_compatible=record.mlx_compatible,
            library_name=record.library_name,
            sibling_files=record.sibling_files,
            last_modified=record.last_modified,
            local_fit_status=record.local_fit_status,
            local_fit_reasons=record.local_fit_reasons,
            estimated_artifact_bytes=record.estimated_artifact_bytes,
            estimated_resident_bytes=record.estimated_resident_bytes,
            parameter_count=record.parameter_count,
            quantization_summary=record.quantization_summary,
            gated=record.gated,
            recommended_action=record.recommended_action,
        )

    @staticmethod
    def _hub_model_card_message(record: HubModelCardRecord) -> maintenance_pb2.HubModelCard:
        return maintenance_pb2.HubModelCard(
            repo_id=record.repo_id,
            author=record.author,
            model_name=record.model_name,
            summary=record.summary,
            license=record.license,
            pipeline_tag=record.pipeline_tag,
            tags=record.tags,
            downloads=record.downloads,
            likes=record.likes,
            mlx_compatible=record.mlx_compatible,
            library_name=record.library_name,
            sibling_files=record.sibling_files,
            base_models=record.base_models,
            last_modified=record.last_modified,
            local_fit_status=record.local_fit_status,
            local_fit_reasons=record.local_fit_reasons,
            estimated_artifact_bytes=record.estimated_artifact_bytes,
            estimated_resident_bytes=record.estimated_resident_bytes,
            parameter_count=record.parameter_count,
            quantization_summary=record.quantization_summary,
            gated=record.gated,
            recommended_action=record.recommended_action,
        )

    def convert_model(
        self,
        request: maintenance_pb2.ConvertModelRequest,
    ) -> Iterator[maintenance_pb2.ConvertModelEvent]:
        operation = request.ext.get("operation")
        if not operation:
            operation = "quantize" if request.weight_quant or request.kv_quant else "convert"

        if operation not in {
            "convert",
            "quantize",
            "download",
            "local_import",
            "upload",
            "build_training_dataset",
            "train_lora",
            "activate_adapter",
            "remove_derived_model",
            "registry_snapshot",
            "dataset_snapshot",
            "dataset_download",
            "dataset_remove",
            "generate_synthetic_dataset",
        }:
            yield maintenance_pb2.ConvertModelEvent(
                failed=maintenance_pb2.ConvertFailed(
                    error=common_pb2.ErrorStatus(
                        code="invalid_argument",
                        message=f"Unsupported model operation: {operation}",
                    )
                )
            )
            return

        if operation == "quantize" and self._registry.runtime_stats().active_requests > 0:
            yield maintenance_pb2.ConvertModelEvent(
                failed=maintenance_pb2.ConvertFailed(
                    error=common_pb2.ErrorStatus(
                        code="resource_locked",
                        message="Quantization is blocked while active inference is running.",
                    )
                )
            )
            return

        lock_scope = self._lock_scope(operation, request)
        held_by = self._operation_locks.try_acquire(lock_scope, operation)
        if held_by is not None:
            yield maintenance_pb2.ConvertModelEvent(
                failed=maintenance_pb2.ConvertFailed(
                    error=common_pb2.ErrorStatus(
                        code="resource_locked",
                        message=f"Operation blocked by active quantization lock on {lock_scope} held by {held_by}.",
                    )
                )
            )
            return

        try:
            job = self._job_registry.start(operation, request.source_model, "")
            output_dir = self._resolved_output_dir(operation, request, job.job_id)
            output_dir.mkdir(parents=True, exist_ok=True)
            self._job_registry.set_output_dir(job.job_id, str(output_dir))
            yield maintenance_pb2.ConvertModelEvent(
                started=maintenance_pb2.ConvertStarted(job_id=job.job_id)
            )

            if operation in {"dataset_snapshot", "dataset_download", "dataset_remove", "generate_synthetic_dataset"}:
                try:
                    result = self._run_dataset_operation(
                        operation=operation,
                        job_id=job.job_id,
                        request=request,
                        output_dir=output_dir,
                    )
                except ModelOperationError as exc:
                    self._job_registry.fail(job.job_id, exc.code, exc.message)
                    yield maintenance_pb2.ConvertModelEvent(
                        failed=maintenance_pb2.ConvertFailed(
                            error=common_pb2.ErrorStatus(
                                code=exc.code,
                                message=exc.message,
                                retriable=exc.retriable,
                                details=exc.details,
                            )
                        )
                    )
                    return

                for stage, pct in result["progress_events"]:
                    self._job_registry.progress(job.job_id, stage, pct)
                    yield maintenance_pb2.ConvertModelEvent(
                        progress=maintenance_pb2.ConvertProgress(stage=stage, pct=pct)
                    )
                manifest_payload = result["manifest"]
                manifest_json = json.dumps(manifest_payload, sort_keys=True)
                artifact_path = output_dir / f"{operation}.json"
                artifact_path.write_text(json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8")
                self._job_registry.attach_manifest(job.job_id, manifest_json)
                if request.generate_manifest:
                    yield maintenance_pb2.ConvertModelEvent(
                        manifest=maintenance_pb2.ConvertManifest(manifest_json=manifest_json)
                    )
                completed_output_path = str(result.get("output_path") or artifact_path)
                self._job_registry.complete(job.job_id, completed_output_path)
                yield maintenance_pb2.ConvertModelEvent(
                    completed=maintenance_pb2.ConvertCompleted(output_path=completed_output_path)
                )
                return

            if operation == "quantize":
                stage_sequence = [
                    ("resolve_source", 0.1),
                    ("normalize_profile", 0.25),
                    ("quantize_weights", 0.5),
                    ("write_bundle", 0.75),
                    ("write_manifest", 0.9),
                ]
                for stage, pct in stage_sequence:
                    self._job_registry.progress(job.job_id, stage, pct)
                    yield maintenance_pb2.ConvertModelEvent(
                        progress=maintenance_pb2.ConvertProgress(stage=stage, pct=pct)
                    )
                if hold_ms := int(request.ext.get("test_hold_ms", "0") or "0"):
                    time.sleep(hold_ms / 1000.0)

                try:
                    result = self._quantization_pipeline.run(
                        request,
                        job_id=job.job_id,
                        output_dir=output_dir,
                    )
                except ModelOperationError as exc:
                    self._job_registry.fail(job.job_id, exc.code, exc.message)
                    yield maintenance_pb2.ConvertModelEvent(
                        failed=maintenance_pb2.ConvertFailed(
                            error=common_pb2.ErrorStatus(
                                code=exc.code,
                                message=exc.message,
                                retriable=exc.retriable,
                                details=exc.details,
                            )
                        )
                    )
                    return
                except Exception as exc:
                    error_code = "quantization_failure"
                    self._job_registry.fail(job.job_id, error_code, str(exc))
                    yield maintenance_pb2.ConvertModelEvent(
                        failed=maintenance_pb2.ConvertFailed(
                            error=common_pb2.ErrorStatus(
                                code=error_code,
                                message=str(exc),
                            )
                        )
                    )
                    return
                manifest_payload = dict(result.manifest_payload)
                manifest_payload["job_id"] = job.job_id
                manifest_payload["artifact_bytes"] = result.artifact_bytes
                manifest_payload["manifest_bytes"] = result.manifest_bytes
                manifest_payload["manifest_path"] = str(result.manifest_path)
                manifest_payload["artifact_path"] = str(result.bundle_path)
                manifest_json = json.dumps(manifest_payload, sort_keys=True)
                artifact_path = result.bundle_path
                worker_profile = self._worker_quant_profile(result.profile)
                worker_artifact = self._worker_artifact(
                    schema_version="melix.quantized_bundle.v1",
                    artifact_kind="quantized_model_bundle",
                    bundle_path=result.bundle_path,
                    manifest_path=result.manifest_path,
                    artifact_bytes=result.artifact_bytes,
                    manifest_bytes=result.manifest_bytes,
                    serving_compatible=True,
                    smoke_test_requested=request.run_smoke_test,
                    smoke_test_passed=result.smoke_test_passed,
                    runtime="mlx_text",
                )
                if request.generate_manifest:
                    self._job_registry.attach_manifest(job.job_id, manifest_json)
                    yield maintenance_pb2.ConvertModelEvent(
                        manifest=maintenance_pb2.ConvertManifest(
                            manifest_json=manifest_json,
                            quant_profile=worker_profile,
                            artifact=worker_artifact,
                        )
                    )
                self._job_registry.complete(job.job_id, str(artifact_path))
                yield maintenance_pb2.ConvertModelEvent(
                    completed=maintenance_pb2.ConvertCompleted(
                        output_path=str(artifact_path),
                        quant_profile=worker_profile,
                        artifact=worker_artifact,
                    )
                )
                return

            if operation == "convert":
                stage_sequence = [
                    ("resolve_source", 0.15),
                    ("package_bundle", 0.5),
                    ("write_manifest", 0.9),
                ]
                for stage, pct in stage_sequence:
                    self._job_registry.progress(job.job_id, stage, pct)
                    yield maintenance_pb2.ConvertModelEvent(
                        progress=maintenance_pb2.ConvertProgress(stage=stage, pct=pct)
                    )

                result = self._conversion_pipeline.run(
                    request,
                    job_id=job.job_id,
                    output_dir=output_dir,
                )
                manifest_payload = dict(result.manifest_payload)
                manifest_payload["job_id"] = job.job_id
                manifest_json = json.dumps(manifest_payload, sort_keys=True)
                worker_artifact = self._worker_artifact(
                    schema_version="melix.converted_model_bundle.v1",
                    artifact_kind="converted_model_bundle",
                    bundle_path=result.bundle_path,
                    manifest_path=result.manifest_path,
                    artifact_bytes=result.artifact_bytes,
                    manifest_bytes=result.manifest_bytes,
                    serving_compatible=True,
                    smoke_test_requested=request.run_smoke_test,
                    smoke_test_passed=result.smoke_test_passed,
                    runtime=result.runtime,
                )
                if request.generate_manifest:
                    self._job_registry.attach_manifest(job.job_id, manifest_json)
                    yield maintenance_pb2.ConvertModelEvent(
                        manifest=maintenance_pb2.ConvertManifest(
                            manifest_json=manifest_json,
                            artifact=worker_artifact,
                        )
                    )

                self._job_registry.complete(job.job_id, str(result.bundle_path))
                yield maintenance_pb2.ConvertModelEvent(
                    completed=maintenance_pb2.ConvertCompleted(
                        output_path=str(result.bundle_path),
                        artifact=worker_artifact,
                    )
                )
                return

            if operation in {"download", "local_import"}:
                try:
                    if operation == "download":
                        result = self._download_pipeline.run(
                            request,
                            job_id=job.job_id,
                            output_dir=output_dir,
                        )
                    else:
                        result = self._local_import_pipeline.run(
                            request,
                            job_id=job.job_id,
                            output_dir=output_dir,
                        )
                except ModelOperationError as exc:
                    state_json = exc.details.get("state_json", "")
                    if state_json:
                        self._job_registry.attach_manifest(job.job_id, state_json)
                        if request.generate_manifest:
                            yield maintenance_pb2.ConvertModelEvent(
                                manifest=maintenance_pb2.ConvertManifest(manifest_json=state_json)
                            )
                    self._job_registry.fail(job.job_id, exc.code, exc.message)
                    yield maintenance_pb2.ConvertModelEvent(
                        failed=maintenance_pb2.ConvertFailed(
                            error=common_pb2.ErrorStatus(
                                code=exc.code,
                                message=exc.message,
                                retriable=exc.retriable,
                                details=exc.details,
                            )
                        )
                    )
                    return

                if operation in {"download", "local_import"}:
                    self._registry.model_catalog.registry_snapshot(rescan=True)

                for snapshot in result.snapshots:
                    self._job_registry.progress(job.job_id, snapshot.stage, snapshot.pct)
                    self._job_registry.attach_manifest(job.job_id, snapshot.manifest_json)
                    yield maintenance_pb2.ConvertModelEvent(
                        progress=maintenance_pb2.ConvertProgress(
                            stage=snapshot.stage,
                            pct=snapshot.pct,
                        )
                    )
                    if request.generate_manifest:
                        yield maintenance_pb2.ConvertModelEvent(
                            manifest=maintenance_pb2.ConvertManifest(manifest_json=snapshot.manifest_json)
                        )

                self._job_registry.complete(job.job_id, str(result.output_path))
                yield maintenance_pb2.ConvertModelEvent(
                    completed=maintenance_pb2.ConvertCompleted(output_path=str(result.output_path))
                )
                return

            if operation == "upload":
                stage_sequence = [
                    ("resolve_artifact", 0.25),
                    ("publish_remote", 0.8),
                ]
                for stage, pct in stage_sequence:
                    self._job_registry.progress(job.job_id, stage, pct)
                    yield maintenance_pb2.ConvertModelEvent(
                        progress=maintenance_pb2.ConvertProgress(stage=stage, pct=pct)
                    )

                try:
                    result = self._upload_receipt_pipeline.run(
                        request,
                        job_id=job.job_id,
                        output_dir=output_dir,
                    )
                except ModelOperationError as exc:
                    self._job_registry.fail(job.job_id, exc.code, exc.message)
                    yield maintenance_pb2.ConvertModelEvent(
                        failed=maintenance_pb2.ConvertFailed(
                            error=common_pb2.ErrorStatus(
                                code=exc.code,
                                message=exc.message,
                                retriable=exc.retriable,
                                details=exc.details,
                            )
                        )
                    )
                    return

                manifest_payload = dict(result.manifest_payload)
                manifest_payload["job_id"] = job.job_id
                manifest_json = json.dumps(manifest_payload, sort_keys=True)
                worker_artifact = self._worker_artifact(
                    schema_version="melix.upload_receipt.v1",
                    artifact_kind="upload_receipt",
                    bundle_path=result.receipt_path,
                    manifest_path=result.receipt_path,
                    artifact_bytes=result.artifact_bytes,
                    manifest_bytes=result.manifest_bytes,
                    serving_compatible=False,
                    smoke_test_requested=False,
                    smoke_test_passed=False,
                    runtime=result.runtime,
                )
                if request.generate_manifest:
                    self._job_registry.attach_manifest(job.job_id, manifest_json)
                    yield maintenance_pb2.ConvertModelEvent(
                        manifest=maintenance_pb2.ConvertManifest(
                            manifest_json=manifest_json,
                            artifact=worker_artifact,
                        )
                    )
                self._job_registry.complete(job.job_id, str(result.receipt_path))
                yield maintenance_pb2.ConvertModelEvent(
                    completed=maintenance_pb2.ConvertCompleted(
                        output_path=str(result.receipt_path),
                        artifact=worker_artifact,
                    )
                )
                return

            if operation in {
                "build_training_dataset",
                "train_lora",
                "activate_adapter",
                "remove_derived_model",
            }:
                try:
                    pipeline_result, progress_events = self._run_specialized_model_operation(
                        operation=operation,
                        job_id=job.job_id,
                        request=request,
                        output_dir=output_dir,
                    )
                except ModelOperationError as exc:
                    self._job_registry.fail(job.job_id, exc.code, exc.message)
                    yield maintenance_pb2.ConvertModelEvent(
                        failed=maintenance_pb2.ConvertFailed(
                            error=common_pb2.ErrorStatus(
                                code=exc.code,
                                message=exc.message,
                                retriable=exc.retriable,
                                details=exc.details,
                            )
                        )
                    )
                    return
                except Exception as exc:
                    error_code = {
                        "build_training_dataset": "dataset_build_failure",
                        "train_lora": "backend_training_failure",
                        "activate_adapter": "activation_failure",
                        "remove_derived_model": "removal_failure",
                    }.get(operation, "runtime_error")
                    self._job_registry.fail(job.job_id, error_code, str(exc))
                    yield maintenance_pb2.ConvertModelEvent(
                        failed=maintenance_pb2.ConvertFailed(
                            error=common_pb2.ErrorStatus(
                                code=error_code,
                                message=str(exc),
                            )
                        )
                    )
                    return

                for stage, pct in progress_events:
                    self._job_registry.progress(job.job_id, stage, pct)
                    yield maintenance_pb2.ConvertModelEvent(
                        progress=maintenance_pb2.ConvertProgress(stage=stage, pct=pct)
                    )

                manifest_json = json.dumps(pipeline_result.manifest, sort_keys=True)
                completed_output_path = getattr(pipeline_result, "output_path", None) or pipeline_result.manifest_path
                self._job_registry.attach_manifest(job.job_id, manifest_json)
                if request.generate_manifest:
                    yield maintenance_pb2.ConvertModelEvent(
                        manifest=maintenance_pb2.ConvertManifest(manifest_json=manifest_json)
                    )

                self._job_registry.complete(
                    job.job_id,
                    str(completed_output_path),
                )
                if operation == "activate_adapter":
                    self._register_derived_model_manifest(pipeline_result.manifest)
                elif operation == "remove_derived_model":
                    self._registry.model_catalog.remove_model(
                        str(pipeline_result.manifest.get("derived_model_id", ""))
                    )
                yield maintenance_pb2.ConvertModelEvent(
                    completed=maintenance_pb2.ConvertCompleted(
                        output_path=str(completed_output_path)
                    )
                )
                return

            self._job_registry.progress(job.job_id, "prepare", 0.25)
            yield maintenance_pb2.ConvertModelEvent(
                progress=maintenance_pb2.ConvertProgress(stage="prepare", pct=0.25)
            )

            artifact_path = self._artifact_path(operation, output_dir)
            if operation == "registry_snapshot":
                registry_roots = _registry_roots_override(request.ext)
                registry_rescan = _registry_rescan_enabled(request.ext)
                manifest_payload = self._job_registry.snapshot(exclude_job_ids={job.job_id})
                manifest_payload.update(
                    {
                        "job_id": job.job_id,
                        "operation": operation,
                        "source_model": request.source_model,
                        "output_dir": str(output_dir),
                        "model_registry": self._registry.model_catalog.registry_snapshot_payload(
                            rescan=registry_rescan,
                            registry_roots=registry_roots,
                        ),
                    }
                )
            else:
                manifest_payload = {
                    "job_id": job.job_id,
                    "operation": operation,
                    "source_model": request.source_model,
                    "output_dir": str(output_dir),
                    "weight_quant": request.weight_quant,
                    "kv_quant": request.kv_quant,
                    "artifact_kind": request.ext.get("artifact_kind", ""),
                    "artifact_path": request.ext.get("artifact_path", ""),
                    "target_repo": request.ext.get("target_repo", ""),
                    "ext": dict(request.ext),
                }
                if operation == "upload":
                    linked_quantization = self._linked_quantization_metadata(request)
                    if linked_quantization is not None:
                        manifest_payload["linked_quantization"] = linked_quantization
            if operation == "train_lora":
                manifest_payload.update(
                    {
                        "adapter_name": request.ext.get("adapter_name", "melix-dev-adapter"),
                        "dataset_uri": request.ext.get("dataset_uri", "datasets/melix-dev"),
                        "training_duration_ms": 1_420.0,
                        "adapter_publish_ms": 118.0,
                    }
                )

            artifact_path.write_text(json.dumps(manifest_payload, indent=2) + "\n")

            self._job_registry.progress(job.job_id, "write_artifact", 0.75)
            yield maintenance_pb2.ConvertModelEvent(
                progress=maintenance_pb2.ConvertProgress(stage="write_artifact", pct=0.75)
            )

            if request.generate_manifest:
                manifest_json = json.dumps(manifest_payload, sort_keys=True)
                self._job_registry.attach_manifest(job.job_id, manifest_json)
                yield maintenance_pb2.ConvertModelEvent(
                    manifest=maintenance_pb2.ConvertManifest(manifest_json=manifest_json)
                )

            self._job_registry.complete(job.job_id, str(artifact_path))
            yield maintenance_pb2.ConvertModelEvent(
                completed=maintenance_pb2.ConvertCompleted(output_path=str(artifact_path))
            )
        finally:
            self._operation_locks.release(lock_scope)

    def get_model_info(
        self,
        request: maintenance_pb2.GetModelInfoRequest,
    ) -> maintenance_pb2.GetModelInfoResponse:
        model = self._registry.model_catalog.get(request.source_model)
        if model is None:
            return maintenance_pb2.GetModelInfoResponse(
                ok=False,
                error=common_pb2.ErrorStatus(code="not_found", message="Unknown source model."),
            )

        ext = dict(model.ext)
        fallback_modalities, fallback_tasks = _default_capability_lists(model.model_kind)
        supported_modalities = _split_capability_values(
            ext.get(_CAPABILITY_SUPPORTED_MODALITIES_KEY, "")
        ) or fallback_modalities
        supported_tasks = _split_capability_values(
            ext.get(_CAPABILITY_SUPPORTED_TASKS_KEY, "")
        ) or fallback_tasks
        supported_parsers = _split_capability_values(
            ext.get(_CAPABILITY_SUPPORTED_PARSERS_KEY, "")
        )
        base_parser = (model.parser_mode or "").strip()
        if base_parser and base_parser not in supported_parsers:
            supported_parsers.insert(0, base_parser)
        tool_parser = ext.get("tool_parser_mode", "").strip()
        if tool_parser and tool_parser not in supported_parsers:
            supported_parsers.append(tool_parser)

        return maintenance_pb2.GetModelInfoResponse(
            ok=True,
            model_kind=model.model_kind,
            max_context=model.max_context,
            supported_parsers=supported_parsers,
            supported_modalities=supported_modalities,
            supported_tasks=supported_tasks,
            backend_id=_model_backend_id(model),
            family_id=_model_family_id(model),
            model_path=model.model_path,
            model_revision=model.revision,
            default_workflow_role=ext.get("melix.image.default_workflow_role", ""),
            detected_identity_source=ext.get("detected_identity_source", ""),
        )

    def search_hub_models(
        self,
        request: maintenance_pb2.SearchHubModelsRequest,
    ) -> maintenance_pb2.SearchHubModelsResponse:
        try:
            page = self._hub_catalog.search_models(
                query=request.query,
                page_size=request.page_size,
                cursor=request.cursor,
                mlx_only=request.mlx_only,
            )
        except HubCatalogError as exc:
            return maintenance_pb2.SearchHubModelsResponse(
                ok=False,
                error=common_pb2.ErrorStatus(
                    code=exc.code,
                    message=exc.message,
                    retriable=exc.retriable,
                ),
            )
        except Exception as exc:
            return maintenance_pb2.SearchHubModelsResponse(
                ok=False,
                error=common_pb2.ErrorStatus(
                    code="hub_request_failed",
                    message=str(exc),
                ),
            )

        response = maintenance_pb2.SearchHubModelsResponse(
            ok=True,
            next_cursor=page.next_cursor,
        )
        items = [
            item
            for item in page.items
            if not request.mlx_only or item.mlx_compatible
        ]
        response.models.extend(self._hub_summary_message(item) for item in items)
        return response

    def get_hub_model_card(
        self,
        request: maintenance_pb2.GetHubModelCardRequest,
    ) -> maintenance_pb2.GetHubModelCardResponse:
        try:
            card = self._hub_catalog.get_model_card(repo_id=request.repo_id)
        except HubCatalogError as exc:
            return maintenance_pb2.GetHubModelCardResponse(
                ok=False,
                error=common_pb2.ErrorStatus(
                    code=exc.code,
                    message=exc.message,
                    retriable=exc.retriable,
                ),
            )
        except Exception as exc:
            return maintenance_pb2.GetHubModelCardResponse(
                ok=False,
                error=common_pb2.ErrorStatus(
                    code="hub_request_failed",
                    message=str(exc),
                ),
            )

        return maintenance_pb2.GetHubModelCardResponse(
            ok=True,
            card=self._hub_model_card_message(card),
        )

    def doctor_response(
        self,
        request: maintenance_pb2.RunDoctorRequest,
    ) -> maintenance_pb2.RunDoctorResponse:
        stats = self._registry.runtime_stats()
        loaded_models = self._registry.list_loaded_models()
        loaded_model = self._registry.get_loaded_model(request.model_handle) if request.model_handle else None
        findings = self._doctor_findings(
            request=request,
            stats=stats,
            loaded_models=loaded_models,
            loaded_model=loaded_model,
        )
        health_status = self._doctor_health_status(findings)
        lines = [
            "# Melix Doctor",
            "",
            "## Runtime",
            f"- worker_state: {stats.worker_state or 'unknown'}",
            f"- active_requests: {stats.active_requests}",
            f"- loaded_models: {len(loaded_models)}",
            f"- resident_bytes: {stats.resident_bytes}",
        ]
        lines.extend(
            [
                "",
                "## Health",
                f"- status: {self._doctor_health_status_label(health_status)}",
            ]
        )
        if findings:
            for finding in findings:
                lines.append(
                    f"- {self._doctor_health_status_label(finding.severity)} {finding.code}: {finding.summary}"
                )
        if request.model_handle:
            lines.append(f"- model_handle: {request.model_handle}")
            if loaded_model is not None:
                identity_lines = self._identity_diagnostic_lines(loaded_model.spec)
                if identity_lines:
                    lines.extend(["", "## Model Identity", *identity_lines])
        if request.include_cache_diagnostics:
            lines.extend(
                [
                    "",
                    "## Cache",
                    f"- l1_cache_bytes: {stats.l1_cache_bytes}",
                    f"- l2_cache_bytes: {stats.l2_cache_bytes}",
                    f"- l1_hit_rate: {stats.l1_hit_rate:.2f}",
                    f"- l2_hit_rate: {stats.l2_hit_rate:.2f}",
                ]
            )
        if request.include_memory_report:
            lines.extend(
                [
                    "",
                    "## Memory",
                    f"- resident_bytes: {stats.resident_bytes}",
                    f"- image_peak_memory_bytes: {stats.last_image_peak_memory_bytes}",
                ]
            )
        return maintenance_pb2.RunDoctorResponse(
            ok=True,
            report_markdown="\n".join(lines) + "\n",
            health_status=health_status,
            findings=findings,
        )

    @staticmethod
    def _identity_diagnostic_lines(model: common_pb2.ModelSpec) -> list[str]:
        effective_family = _model_family_id(model)
        model_architecture = model.ext.get("model_architecture", "")
        detected_architecture = model.ext.get("detected_architecture", "")
        detected_family_id = model.ext.get("detected_family_id", "")
        detected_identity_source = model.ext.get("detected_identity_source", "")
        identity_override = model.ext.get("identity_override", "")

        if not any(
            [
                effective_family,
                model_architecture,
                detected_architecture,
                detected_family_id,
                detected_identity_source,
                identity_override,
            ]
        ):
            return []

        lines = [
            f"- model_id: {model.model_id}",
            f"- model_kind: {model.model_kind}",
        ]
        if model_architecture:
            lines.append(f"- model_architecture: {model_architecture}")
        if effective_family:
            lines.append(f"- effective_family_id: {effective_family}")
        if detected_architecture:
            lines.append(f"- detected_architecture: {detected_architecture}")
        if detected_family_id:
            lines.append(f"- detected_family_id: {detected_family_id}")
        if detected_identity_source:
            lines.append(f"- detected_identity_source: {detected_identity_source}")
        if identity_override:
            lines.append(f"- identity_override: {identity_override}")
        return lines

    @staticmethod
    def _doctor_finding(
        code: str,
        severity: maintenance_pb2.HealthStatus,
        summary: str,
        detail: str = "",
    ) -> maintenance_pb2.DoctorFinding:
        return maintenance_pb2.DoctorFinding(
            code=code,
            severity=severity,
            summary=summary,
            detail=detail,
        )

    def _doctor_findings(
        self,
        request: maintenance_pb2.RunDoctorRequest,
        stats,
        loaded_models,
        loaded_model,
    ) -> list[maintenance_pb2.DoctorFinding]:
        findings: list[maintenance_pb2.DoctorFinding] = []
        worker_state = (stats.worker_state or "").strip().lower()

        if worker_state in {"failed", "error"}:
            findings.append(
                self._doctor_finding(
                    code="worker_failed",
                    severity=maintenance_pb2.HEALTH_STATUS_FAILED,
                    summary="Worker runtime is in a failed state.",
                    detail=f"worker_state={stats.worker_state}",
                )
            )

        if request.model_handle and loaded_model is None:
            findings.append(
                self._doctor_finding(
                    code="model_not_loaded",
                    severity=maintenance_pb2.HEALTH_STATUS_DEGRADED,
                    summary="Requested model handle is not loaded in the worker registry.",
                    detail=request.model_handle,
                )
            )

        if (
            request.include_cache_diagnostics
            and loaded_models
            and stats.l1_cache_bytes == 0
            and stats.l2_cache_bytes == 0
        ):
            findings.append(
                self._doctor_finding(
                    code="cache_unavailable",
                    severity=maintenance_pb2.HEALTH_STATUS_WARNING,
                    summary="Cache diagnostics report zero cache bytes while models are loaded.",
                    detail="Both L1 and L2 cache bytes are zero.",
                )
            )

        if request.include_memory_report and loaded_models and stats.resident_bytes == 0:
            findings.append(
                self._doctor_finding(
                    code="resident_bytes_zero",
                    severity=maintenance_pb2.HEALTH_STATUS_WARNING,
                    summary="Resident memory is zero while models are loaded.",
                    detail="Inspect worker memory accounting or reload the affected model.",
                )
            )

        return findings

    def _doctor_health_status(
        self,
        findings: list[maintenance_pb2.DoctorFinding],
    ) -> maintenance_pb2.HealthStatus:
        if not findings:
            return maintenance_pb2.HEALTH_STATUS_HEALTHY
        return max(findings, key=lambda finding: _health_status_rank(finding.severity)).severity

    @staticmethod
    def _doctor_health_status_label(status: maintenance_pb2.HealthStatus) -> str:
        if status == maintenance_pb2.HEALTH_STATUS_HEALTHY:
            return "healthy"
        if status == maintenance_pb2.HEALTH_STATUS_WARNING:
            return "warning"
        if status == maintenance_pb2.HEALTH_STATUS_DEGRADED:
            return "degraded"
        if status == maintenance_pb2.HEALTH_STATUS_FAILED:
            return "failed"
        return "unknown"

    def bench_events(
        self,
        request: maintenance_pb2.RunBenchRequest,
    ) -> Iterator[maintenance_pb2.RunBenchEvent]:
        from worker.productization.benchmark_schemas import (
            build_serving_benchmark_job,
            build_serving_benchmark_results,
        )
        from worker.productization.benchmark_store import BenchmarkStore
        from worker.productization.probe_policy import ProbePolicy

        suites = list(request.suites) or ["smoke"]
        raw_parameters = getattr(request, "parameters", None)
        parameters = dict(raw_parameters) if raw_parameters else {}
        bench_root = (self._jobs_root / "bench").resolve()
        bench_root.mkdir(parents=True, exist_ok=True)

        job = self._job_registry.start("bench", request.model_handle or "runtime", "")
        output_dir = (bench_root / "runs" / job.job_id).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        self._job_registry.set_output_dir(job.job_id, str(output_dir))
        queued_at = int(time.time() * 1000)
        self._benchmark_queue_store.enqueue(
            queue_root=bench_root / "queue",
            record=BenchmarkQueueRecord(
                queue_item_id=job.job_id,
                job_kind="benchmark",
                model_id=(request.model_handle or "runtime").split("::", 1)[0],
                suite_ids=tuple(suites),
                parameters=parameters,
                status="queued",
                created_at_unix_ms=queued_at,
                updated_at_unix_ms=queued_at,
            ),
        )
        yield maintenance_pb2.RunBenchEvent(started=maintenance_pb2.BenchStarted(job_id=job.job_id))
        self._benchmark_queue_store.transition(
            queue_root=bench_root / "queue",
            queue_item_id=job.job_id,
            status="running",
            updated_at_unix_ms=queued_at + 1,
        )

        metrics: list[BenchMetricSpec] = []
        suite_metadata: dict[str, dict[str, object]] = {}
        text_context_rows: list[dict[str, object]] = []
        text_batch_rows: list[dict[str, object]] = []
        text_request_latencies: list[float] = []
        lazy_model_handle = ""
        loaded_model = None
        if self._benchmark_store is None:
            self._benchmark_store = BenchmarkStore(probe_policy=ProbePolicy.evidence())
        telemetry_session = self._benchmark_store.start_telemetry_session(run_id=job.job_id)
        try:
            resolved_model = self._resolve_benchmark_loaded_model(request.model_handle)
            lazy_model_handle = resolved_model.lazy_model_handle
            loaded_model = resolved_model.loaded_model
            runtime_evidence = self._runtime_evidence_for_loaded_model(loaded_model)
            parameters.update(runtime_evidence)
            if self._truthy_parameter(parameters, "require_live_model"):
                self._validate_required_live_model(runtime_evidence, operation="benchmark")
            task_kind = self._resolved_benchmark_task_kind(
                request=request,
                parameters=parameters,
                loaded_model=loaded_model,
            )
            for index, suite in enumerate(suites, start=1):
                pct = index / max(len(suites), 1)
                self._job_registry.progress(job.job_id, suite, pct)
                yield maintenance_pb2.RunBenchEvent(
                    progress=maintenance_pb2.BenchProgress(suite=suite, pct=pct)
                )
                dataset_started_at = time.perf_counter()
                resolved_suite = self._benchmark_suite_catalog.resolve_suite(
                    suite,
                    jobs_root=self._jobs_root,
                    parameters=parameters,
                    task_kind=task_kind,
                )
                dataset_materialize_ms = round((time.perf_counter() - dataset_started_at) * 1_000.0, 2)
                suite_metadata[resolved_suite.suite_id] = resolved_suite.metadata()
                if task_kind == "text-generation":
                    suite_metrics, suite_context_rows, suite_batch_rows, suite_request_latencies = self._measure_text_bench_metrics(
                        loaded_model=loaded_model,
                        suite=resolved_suite,
                        parameters=parameters,
                        job_id=job.job_id,
                        source_repo=request.source_repo,
                        task_kind=task_kind,
                        dataset_materialize_ms=dataset_materialize_ms,
                    )
                    text_context_rows.extend(suite_context_rows)
                    text_batch_rows.extend(suite_batch_rows)
                    text_request_latencies.extend(suite_request_latencies)
                elif task_kind in {"image-to-text", "image-text-to-text"}:
                    suite_metrics = self._measure_vlm_bench_metrics(
                        loaded_model=loaded_model,
                        suite=resolved_suite,
                        parameters=parameters,
                    )
                elif task_kind == "text-to-image":
                    suite_metrics = self._measure_image_generation_bench_metrics(
                        loaded_model=loaded_model,
                        suite=resolved_suite,
                        parameters=parameters,
                    )
                elif task_kind == "image-text-to-image":
                    suite_metrics = self._measure_image_edit_bench_metrics(
                        loaded_model=loaded_model,
                        suite=resolved_suite,
                        parameters=parameters,
                    )
                else:
                    raise ModelOperationError(
                        code="unsupported_task_family",
                        message=f"Unsupported benchmark task kind: {task_kind}",
                        details={"task_kind": task_kind},
                    )
                for metric in suite_metrics:
                    metrics.append(metric)
                    yield maintenance_pb2.RunBenchEvent(
                        metric=maintenance_pb2.BenchMetric(
                            name=metric.name,
                            value=metric.value,
                            unit=metric.unit,
                        )
                    )

            completed_at = int(time.time() * 1000)
            model_id = (request.model_handle or lazy_model_handle or "runtime").split("::", 1)[0]
            context_lengths = tuple(
                sorted(
                    {
                        int(row.get("context_length", 0) or 0)
                        for row in text_context_rows
                        if int(row.get("context_length", 0) or 0) > 0
                    }
                )
            )
            batch_sizes = tuple(
                sorted(
                    {
                        int(row.get("batch_size", 0) or 0)
                        for row in text_batch_rows
                        if int(row.get("batch_size", 0) or 0) > 0
                    }
                )
            )
            request_p50_ms, request_p95_ms = self._percentiles(text_request_latencies, 50.0, 95.0)
            generation_length = self._benchmark_generation_length(parameters)
            repeats = self._benchmark_repeats(parameters)
            cache_profile = self._benchmark_cache_profile(parameters)
            reasoning_mode = parameters.get("reasoning_mode", "").strip()
            structured_output_mode = parameters.get("structured_output_mode", "").strip()
            report_path = output_dir / "bench-report.md"
            report_markdown = self._render_bench_report(
                request,
                metrics,
                task_kind=task_kind,
                parameters=parameters,
                model_memory_summary=self._model_memory_summary(
                    loaded_model=loaded_model,
                    load_triggered_by_run=resolved_model.load_triggered_by_run,
                    load_rss_before_bytes=resolved_model.load_rss_before_bytes,
                    load_rss_after_bytes=resolved_model.load_rss_after_bytes,
                ),
            )
            report_path.write_text(report_markdown, encoding="utf-8")
            job_record = build_serving_benchmark_job(
                job_id=job.job_id,
                model_id=model_id,
                task_kind=task_kind,
                source_repo=request.source_repo,
                suites=tuple(suites),
                context_lengths=context_lengths,
                generation_length=generation_length,
                batch_sizes=batch_sizes,
                repeats=repeats,
                cache_profile=cache_profile,
                reasoning_mode=reasoning_mode,
                structured_output_mode=structured_output_mode,
                request_p50_ms=request_p50_ms,
                request_p95_ms=request_p95_ms,
                parameters=parameters,
                status="completed",
                output_dir=str(output_dir),
                created_at_unix_ms=queued_at,
                updated_at_unix_ms=completed_at,
                suite_metadata=suite_metadata,
            )
            result_records = build_serving_benchmark_results(
                job_id=job.job_id,
                metrics={metric.name: metric.value for metric in metrics},
                units={metric.name: metric.unit for metric in metrics},
                report_path=str(report_path),
                report_markdown=report_markdown,
            )
            telemetry_collection = telemetry_session.finish(
                artifact_root=output_dir,
                output_token_count=BenchmarkStore._output_token_count(
                    tuple(text_context_rows),
                    tuple(text_batch_rows),
                ),
            )
            persisted_paths = self._benchmark_store.persist_serving_benchmark(
                jobs_root=output_dir,
                job=job_record,
                results=result_records,
                context_rows=text_context_rows,
                batch_rows=text_batch_rows,
                telemetry_collection=telemetry_collection,
                model_memory_summary=self._model_memory_summary(
                    loaded_model=loaded_model,
                    load_triggered_by_run=resolved_model.load_triggered_by_run,
                    load_rss_before_bytes=resolved_model.load_rss_before_bytes,
                    load_rss_after_bytes=resolved_model.load_rss_after_bytes,
                ),
            )
            (output_dir / "bench-summary.json").write_text(
                json.dumps(job_record.to_dict(), indent=2) + "\n",
                encoding="utf-8",
            )
            self._job_registry.complete(job.job_id, str(report_path))
            self._benchmark_queue_store.transition(
                queue_root=bench_root / "queue",
                queue_item_id=job.job_id,
                status="completed",
                updated_at_unix_ms=completed_at,
            )
            yield maintenance_pb2.RunBenchEvent(
                completed=maintenance_pb2.BenchCompleted(
                    report_path=str(report_path),
                    evidence_path=str(persisted_paths.get("evidence", "")),
                )
            )
        finally:
            telemetry_session.cancel()
            if lazy_model_handle and loaded_model is not None and lazy_model_handle == loaded_model.handle:
                self._registry.unload_model(lazy_model_handle)

    def bench_matrix_response(
        self,
        request: maintenance_pb2.RunBenchMatrixRequest,
    ) -> maintenance_pb2.RunBenchMatrixResponse:
        from worker.productization.benchmark_schemas import (
            build_benchmark_matrix_job,
            build_benchmark_matrix_request_row,
            build_benchmark_matrix_summary_row,
        )
        from worker.productization.benchmark_store import BenchmarkStore

        suite_ids = self._normalized_string_values(request.suite_ids, default=("smoke",))
        context_lengths = self._positive_sorted_values(request.context_lengths, default=(1024,))
        generation_lengths = self._positive_sorted_values(request.generation_lengths, default=(128,))
        batch_sizes = self._positive_sorted_values(request.batch_sizes, default=(1,))
        cache_profiles = self._normalized_string_values(request.cache_profiles, default=("cold",))
        reasoning_modes = self._normalized_string_values(request.reasoning_modes, default=("default",))
        structured_output_modes = self._normalized_string_values(
            request.structured_output_modes,
            default=("plain_text",),
        )
        concurrency_levels = self._positive_sorted_values(request.concurrency_levels, default=(1,))
        repeats = max(int(request.repeats or 0), 1)
        requests = int(request.requests or 0)
        duration_seconds = int(request.duration_seconds or 0)
        if (requests > 0) == (duration_seconds > 0):
            raise ModelOperationError(
                code="invalid_argument",
                message="Provide exactly one matrix load budget.",
                details={"requests": requests, "duration_seconds": duration_seconds},
            )

        bench_root = (self._jobs_root / "bench").resolve()
        bench_root.mkdir(parents=True, exist_ok=True)

        job = self._job_registry.start("bench-matrix", request.model_handle or "runtime", "")
        output_dir = (bench_root / "matrix-runs" / job.job_id).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        self._job_registry.set_output_dir(job.job_id, str(output_dir))
        queued_at = int(time.time() * 1000)
        queue_parameters = {
            "context_lengths": ",".join(str(value) for value in context_lengths),
            "generation_lengths": ",".join(str(value) for value in generation_lengths),
            "batch_sizes": ",".join(str(value) for value in batch_sizes),
            "cache_profiles": ",".join(cache_profiles),
            "reasoning_modes": ",".join(reasoning_modes),
            "structured_output_modes": ",".join(structured_output_modes),
            "concurrency_levels": ",".join(str(value) for value in concurrency_levels),
            "repeats": str(repeats),
            "requests": str(requests),
            "duration_seconds": str(duration_seconds),
        }
        self._benchmark_queue_store.enqueue(
            queue_root=bench_root / "matrix-queue",
            record=BenchmarkQueueRecord(
                queue_item_id=job.job_id,
                job_kind="benchmark_matrix",
                model_id=(request.model_handle or "runtime").split("::", 1)[0],
                suite_ids=tuple(suite_ids),
                parameters=queue_parameters,
                status="queued",
                created_at_unix_ms=queued_at,
                updated_at_unix_ms=queued_at,
            ),
        )
        self._benchmark_queue_store.transition(
            queue_root=bench_root / "matrix-queue",
            queue_item_id=job.job_id,
            status="running",
            updated_at_unix_ms=queued_at + 1,
        )

        lazy_model_handle = ""
        loaded_model = None
        try:
            resolved_model = self._resolve_benchmark_loaded_model(request.model_handle)
            lazy_model_handle = resolved_model.lazy_model_handle
            loaded_model = resolved_model.loaded_model
            runtime_evidence = self._runtime_evidence_for_loaded_model(loaded_model)
            matrix_parameters = {**queue_parameters, **runtime_evidence}
            task_kind = self._resolved_benchmark_matrix_task_kind(
                request=request,
                loaded_model=loaded_model,
            )
            if task_kind not in {"text-generation", "image-to-text", "image-text-to-text"}:
                raise ModelOperationError(
                    code="unsupported_task_family",
                    message=f"Unsupported benchmark matrix task kind: {task_kind}",
                    details={"task_kind": task_kind},
                )

            model_id = (request.model_handle or lazy_model_handle or "runtime").split("::", 1)[0]
            summary_rows = []
            request_rows = []
            cell_counter = 0
            for suite_id in suite_ids:
                dataset_started_at = time.perf_counter()
                resolved_suite = self._benchmark_suite_catalog.resolve_suite(
                    suite_id,
                    jobs_root=self._jobs_root,
                    parameters={},
                    task_kind=task_kind,
                )
                dataset_materialize_ms = round((time.perf_counter() - dataset_started_at) * 1_000.0, 2)
                cases = list(resolved_suite.cases)
                for context_length in context_lengths:
                    for generation_length in generation_lengths:
                        for batch_size in batch_sizes:
                            for cache_profile in cache_profiles:
                                for reasoning_mode in reasoning_modes:
                                    for structured_output_mode in structured_output_modes:
                                        for concurrency_level in concurrency_levels:
                                            cell_started_at = time.perf_counter()
                                            cell_counter += 1
                                            cell_id = f"cell-{cell_counter}"
                                            row_count = self._benchmark_matrix_request_count(
                                                requests=requests,
                                                duration_seconds=duration_seconds,
                                                repeats=repeats,
                                                concurrency_level=concurrency_level,
                                            )
                                            cell_rows = []
                                            for request_index in range(row_count):
                                                repeat_index = request_index % repeats
                                                created_at_unix_ms = int(time.time() * 1000)
                                                case = (
                                                    cases[request_index % len(cases)]
                                                    if cases
                                                    else None
                                                )
                                                tool_run = None
                                                try:
                                                    tool_run = self._agentic_tool_run_for_benchmark_case(case)
                                                    sample = self._measure_benchmark_matrix_sample(
                                                        loaded_model=loaded_model,
                                                        suite=resolved_suite,
                                                        case=case,
                                                        task_kind=task_kind,
                                                        context_length=context_length,
                                                        generation_length=generation_length,
                                                        batch_size=batch_size,
                                                        repeat_index=repeat_index,
                                                        cache_profile=cache_profile,
                                                        reasoning_mode=reasoning_mode,
                                                        structured_output_mode=structured_output_mode,
                                                    )
                                                    row = build_benchmark_matrix_request_row(
                                                        job_id=job.job_id,
                                                        cell_id=cell_id,
                                                        task_kind=task_kind,
                                                        suite_id=resolved_suite.suite_id,
                                                        context_length=context_length,
                                                        generation_length=generation_length,
                                                        batch_size=batch_size,
                                                        cache_profile=cache_profile,
                                                        reasoning_mode=reasoning_mode,
                                                        structured_output_mode=structured_output_mode,
                                                        concurrency_level=concurrency_level,
                                                        repeat_index=repeat_index,
                                                        request_index=request_index,
                                                        ttft_ms=sample.ttft_ms,
                                                        request_latency_ms=sample.request_latency_ms,
                                                        prefill_tokens_per_second=sample.prefill_tokens_per_second,
                                                        decode_tokens_per_second=sample.decode_tokens_per_second,
                                                        queue_wait_ms=0.0,
                                                        peak_memory_bytes=int(sample.peak_memory_bytes),
                                                        status="completed",
                                                        error_code="",
                                                        created_at_unix_ms=created_at_unix_ms,
                                                        dataset_materialize_ms=dataset_materialize_ms,
                                                        prompt_render_ms=sample.prompt_render_ms,
                                                        warmup_ms=sample.warmup_ms,
                                                        prefill_ms=sample.prefill_ms,
                                                        decode_ms=sample.decode_ms,
                                                        tokens_in=sample.prompt_tokens,
                                                        tokens_out=sample.completion_tokens,
                                                        first_token_index=sample.first_token_index,
                                                        cache_hit=sample.cache_hit,
                                                        runtime_kind=sample.runtime_kind,
                                                        error_stage=sample.error_stage,
                                                        speculative_acceptance_rate=sample.speculative_acceptance_rate,
                                                        speculative_rollback_rate=sample.speculative_rollback_rate,
                                                        speculative_accepted_tokens=sample.speculative_accepted_tokens,
                                                        speculative_rejected_tokens=sample.speculative_rejected_tokens,
                                                        speculative_fallback_count=sample.speculative_fallback_count,
                                                        speculative_num_draft_tokens=sample.speculative_num_draft_tokens,
                                                        speculative_draft_model_configured=sample.speculative_draft_model_configured,
                                                        speculative_draft_propose_ms=sample.speculative_draft_propose_ms,
                                                        speculative_target_verify_ms=sample.speculative_target_verify_ms,
                                                        dflash_enabled=sample.dflash_enabled,
                                                        dflash_block_size=sample.dflash_block_size,
                                                        dflash_rollback_count=sample.dflash_rollback_count,
                                                        dflash_target_hidden_layers=sample.dflash_target_hidden_layers,
                                                        **self._agentic_tool_kwargs(tool_run),
                                                    )
                                                except Exception as exc:
                                                    row = build_benchmark_matrix_request_row(
                                                        job_id=job.job_id,
                                                        cell_id=cell_id,
                                                        task_kind=task_kind,
                                                        suite_id=resolved_suite.suite_id,
                                                        context_length=context_length,
                                                        generation_length=generation_length,
                                                        batch_size=batch_size,
                                                        cache_profile=cache_profile,
                                                        reasoning_mode=reasoning_mode,
                                                        structured_output_mode=structured_output_mode,
                                                        concurrency_level=concurrency_level,
                                                        repeat_index=repeat_index,
                                                        request_index=request_index,
                                                        ttft_ms=0.0,
                                                        request_latency_ms=0.0,
                                                        prefill_tokens_per_second=0.0,
                                                        decode_tokens_per_second=0.0,
                                                        queue_wait_ms=0.0,
                                                        peak_memory_bytes=0,
                                                        status="failed",
                                                        error_code=getattr(exc, "code", "runtime_error"),
                                                        created_at_unix_ms=created_at_unix_ms,
                                                        dataset_materialize_ms=dataset_materialize_ms,
                                                        runtime_kind=getattr(loaded_model, "runtime_kind", ""),
                                                        error_stage=self._benchmark_error_stage(exc),
                                                        **self._agentic_tool_kwargs(tool_run),
                                                    )
                                                cell_rows.append(row)
                                                request_rows.append(row)

                                            completed_rows = [row for row in cell_rows if row.status == "completed"]
                                            request_latencies = [row.request_latency_ms for row in completed_rows]
                                            ttft_values = [row.ttft_ms for row in completed_rows]
                                            prefill_values = [
                                                row.prefill_tokens_per_second for row in completed_rows
                                            ]
                                            decode_values = [
                                                row.decode_tokens_per_second for row in completed_rows
                                            ]
                                            queue_wait_values = [row.queue_wait_ms for row in completed_rows]
                                            peak_memory_values = [
                                                float(row.peak_memory_bytes) for row in completed_rows
                                            ]
                                            total_latency_seconds = sum(request_latencies) / 1_000.0
                                            throughput_requests_per_second = (
                                                len(completed_rows) / max(total_latency_seconds, 0.001)
                                                if completed_rows
                                                else 0.0
                                            )
                                            decode_mean = self._mean(decode_values)
                                            ttft_p50_ms, ttft_p95_ms = self._percentiles(ttft_values, 50.0, 95.0)
                                            request_latency_p50_ms, request_latency_p95_ms = self._percentiles(
                                                request_latencies,
                                                50.0,
                                                95.0,
                                            )

                                            summary_rows.append(
                                                build_benchmark_matrix_summary_row(
                                                    job_id=job.job_id,
                                                    task_kind=task_kind,
                                                    source_repo=request.source_repo,
                                                    model_id=model_id,
                                                    suite_id=resolved_suite.suite_id,
                                                    context_length=context_length,
                                                    generation_length=generation_length,
                                                    batch_size=batch_size,
                                                    cache_profile=cache_profile,
                                                    reasoning_mode=reasoning_mode,
                                                    structured_output_mode=structured_output_mode,
                                                    concurrency_level=concurrency_level,
                                                    repeats=repeats,
                                                    requests=requests,
                                                    duration_seconds=duration_seconds,
                                                    ttft_mean_ms=self._mean(ttft_values),
                                                    ttft_std_ms=self._stddev(ttft_values),
                                                    request_latency_mean_ms=self._mean(request_latencies),
                                                    request_latency_std_ms=self._stddev(request_latencies),
                                                    prefill_tokens_per_second_mean=self._mean(prefill_values),
                                                    decode_tokens_per_second_mean=decode_mean,
                                                    throughput_requests_per_second=round(
                                                        throughput_requests_per_second,
                                                        2,
                                                    ),
                                                    throughput_tokens_per_second=round(
                                                        decode_mean * throughput_requests_per_second,
                                                        2,
                                                    ),
                                                    success_rate=round(
                                                        len(completed_rows) / max(len(cell_rows), 1),
                                                        4,
                                                    ),
                                                    peak_memory_bytes_max=int(max(peak_memory_values, default=0.0)),
                                                    queue_wait_mean_ms=self._mean(queue_wait_values),
                                                    queue_wait_p95_ms=self._percentile(queue_wait_values, 95.0),
                                                    cell_wall_ms=round((time.perf_counter() - cell_started_at) * 1_000.0, 2),
                                                    completed_count=len(completed_rows),
                                                    failed_count=len(cell_rows) - len(completed_rows),
                                                    ttft_p50_ms=ttft_p50_ms,
                                                    ttft_p95_ms=ttft_p95_ms,
                                                    request_latency_p50_ms=request_latency_p50_ms,
                                                    request_latency_p95_ms=request_latency_p95_ms,
                                                    created_at_unix_ms=queued_at,
                                                )
                                            )

            completed_at = int(time.time() * 1000)
            job_record = build_benchmark_matrix_job(
                job_id=job.job_id,
                model_id=model_id,
                task_kind=task_kind,
                source_repo=request.source_repo,
                suite_ids=suite_ids,
                status="completed",
                output_dir=str(output_dir),
                created_at_unix_ms=queued_at,
                updated_at_unix_ms=completed_at,
                parameters=matrix_parameters,
            )
            if self._benchmark_store is None:
                self._benchmark_store = BenchmarkStore()
            self._benchmark_store.persist_benchmark_matrix(
                jobs_root=output_dir,
                job=job_record,
                summary_rows=tuple(summary_rows),
                request_rows=tuple(request_rows),
            )
            self._job_registry.complete(job.job_id, str(output_dir / "bench-matrix-summary.csv"))
            self._benchmark_queue_store.transition(
                queue_root=bench_root / "matrix-queue",
                queue_item_id=job.job_id,
                status="completed",
                updated_at_unix_ms=completed_at,
            )

            response = maintenance_pb2.RunBenchMatrixResponse()
            response.job.schema_version = job_record.schema_version
            response.job.job_id = job_record.job_id
            response.job.model_id = job_record.model_id
            response.job.task_kind = job_record.task_kind
            response.job.source_repo = job_record.source_repo
            response.job.suite_ids.extend(job_record.suite_ids)
            response.job.benchmark_mode = job_record.benchmark_mode
            response.job.status = job_record.status
            response.job.output_dir = job_record.output_dir
            response.job.created_at_unix_ms = job_record.created_at_unix_ms
            response.job.updated_at_unix_ms = job_record.updated_at_unix_ms
            for row in summary_rows:
                row_message = response.summary_rows.add()
                row_message.job_id = row.job_id
                row_message.task_kind = row.task_kind
                row_message.source_repo = row.source_repo
                row_message.model_id = row.model_id
                row_message.suite_id = row.suite_id
                row_message.context_length = row.context_length
                row_message.generation_length = row.generation_length
                row_message.batch_size = row.batch_size
                row_message.cache_profile = row.cache_profile
                row_message.reasoning_mode = row.reasoning_mode
                row_message.structured_output_mode = row.structured_output_mode
                row_message.concurrency_level = row.concurrency_level
                row_message.repeats = row.repeats
                row_message.requests = row.requests
                row_message.duration_seconds = row.duration_seconds
                row_message.ttft_mean_ms = row.ttft_mean_ms
                row_message.ttft_std_ms = row.ttft_std_ms
                row_message.request_latency_mean_ms = row.request_latency_mean_ms
                row_message.request_latency_std_ms = row.request_latency_std_ms
                row_message.prefill_tokens_per_second_mean = row.prefill_tokens_per_second_mean
                row_message.decode_tokens_per_second_mean = row.decode_tokens_per_second_mean
                row_message.throughput_requests_per_second = row.throughput_requests_per_second
                row_message.throughput_tokens_per_second = row.throughput_tokens_per_second
                row_message.success_rate = row.success_rate
                row_message.peak_memory_bytes_max = row.peak_memory_bytes_max
                row_message.queue_wait_mean_ms = row.queue_wait_mean_ms
                row_message.queue_wait_p95_ms = row.queue_wait_p95_ms
                row_message.created_at_unix_ms = row.created_at_unix_ms
            return response
        except Exception as exc:
            completed_at = int(time.time() * 1000)
            self._job_registry.fail(job.job_id, getattr(exc, "code", "runtime_error"), str(exc))
            self._benchmark_queue_store.transition(
                queue_root=bench_root / "matrix-queue",
                queue_item_id=job.job_id,
                status="failed",
                updated_at_unix_ms=completed_at,
            )
            raise
        finally:
            if lazy_model_handle and loaded_model is not None and lazy_model_handle == loaded_model.handle:
                self._registry.unload_model(lazy_model_handle)

    @staticmethod
    def _artifact_path(operation: str, output_dir: Path) -> Path:
        filename = {
            "convert": "convert.artifact",
            "quantize": "quantize.artifact",
            "download": "download.artifact",
            "upload": "upload.receipt.json",
            "train_lora": "train_lora.adapter.json",
            "activate_adapter": "activate_adapter.derived_model.json",
            "remove_derived_model": "remove_derived_model.lifecycle.json",
            "registry_snapshot": "registry_snapshot.json",
            "dataset_snapshot": "dataset_snapshot.json",
            "dataset_download": "dataset_download.json",
            "dataset_remove": "dataset_remove.json",
            "generate_synthetic_dataset": "generate_synthetic_dataset.json",
        }[operation]
        return output_dir / filename

    def _resolved_output_dir(
        self,
        operation: str,
        request: maintenance_pb2.ConvertModelRequest,
        job_id: str,
    ) -> Path:
        if operation in {"train_lora", "activate_adapter", "remove_derived_model"}:
            return (self._jobs_root / operation / job_id).resolve()
        return Path(request.output_dir or self._jobs_root / operation).resolve()

    def _lock_scope(self, operation: str, request: maintenance_pb2.ConvertModelRequest) -> str:
        if operation in {"quantize", "upload"}:
            linked_quantization = self._linked_quantization_metadata(request)
            if linked_quantization is not None:
                linked_scope = str(linked_quantization.get("protected_scope", "")).strip()
                if linked_scope:
                    return linked_scope
                linked_source_model = str(linked_quantization.get("source_model", "")).strip()
                if linked_source_model:
                    return f"model-family:{linked_source_model}"

            source_model_spec = self._registry.model_catalog.get(request.source_model)
            protected_scope = protected_scope_for_request(
                request,
                source_model_spec=source_model_spec,
            )
            if protected_scope:
                return protected_scope

        if operation == "upload":
            return request.ext.get("artifact_path", "") or request.source_model or operation
        if operation == "activate_adapter":
            return request.ext.get("artifact_path", "") or request.source_model or operation
        if operation == "remove_derived_model":
            return (
                request.ext.get("derived_model_id", "")
                or request.ext.get("manifest_path", "")
                or request.ext.get("derived_model_manifest_path", "")
                or request.source_model
                or operation
            )
        if operation in {"dataset_download", "dataset_remove", "dataset_snapshot", "generate_synthetic_dataset"}:
            return (
                request.ext.get("synthetic_dataset_id", "")
                or request.ext.get("melix.hf_dataset_repo_id", "")
                or request.ext.get("repo_id", "")
                or request.source_model
                or operation
            )
        return request.source_model or operation

    def _run_dataset_operation(
        self,
        *,
        operation: str,
        job_id: str,
        request: maintenance_pb2.ConvertModelRequest,
        output_dir: Path,
    ) -> dict[str, Any]:
        ext = dict(request.ext)
        progress_events: list[tuple[str, float]] = [("prepare", 0.1)]
        if operation == "dataset_snapshot":
            repo_id = ext.get("melix.hf_dataset_repo_id", "").strip() or ext.get("repo_id", "").strip()
            revision = ext.get("melix.hf_revision", "").strip() or ext.get("revision", "").strip()
            manifest = {
                "schema_version": "melix.dataset_operation.v1",
                "operation": operation,
                "job_id": job_id,
                "source_model": request.source_model,
                "output_dir": str(output_dir),
                "dataset_registry": self._dataset_catalog.registry_snapshot_payload(
                    repo_id=repo_id,
                    revision=revision,
                ),
            }
            progress_events.append(("scan", 1.0))
            return {
                "manifest": manifest,
                "progress_events": progress_events,
                "output_path": output_dir / "dataset_snapshot.json",
            }

        if operation == "dataset_download":
            repo_id = ext.get("melix.hf_dataset_repo_id", "").strip() or request.source_model.strip()
            revision = ext.get("melix.hf_revision", "").strip() or "main"
            result = self._dataset_catalog.download_hf_dataset(
                repo_id=repo_id,
                revision=revision,
                hf_token=ext.get("melix.hf_token", "").strip() or ext.get("hf_token", "").strip(),
                job_id=job_id,
                output_dir=output_dir,
            )
            progress_events.append(("materialize", 1.0))
            return {
                "manifest": result.manifest,
                "progress_events": progress_events,
                "output_path": result.snapshot.snapshot_path,
            }

        if operation == "dataset_remove":
            repo_id = ext.get("melix.hf_dataset_repo_id", "").strip() or ext.get("repo_id", "").strip() or request.source_model.strip()
            result = self._dataset_catalog.remove_hf_dataset_snapshot(
                repo_id=repo_id,
                revision=ext.get("melix.hf_revision", "").strip() or ext.get("revision", "").strip(),
                snapshot_id=ext.get("melix.hf_snapshot_id", "").strip() or ext.get("snapshot_id", "").strip(),
                job_id=job_id,
                output_dir=output_dir,
            )
            progress_events.append(("remove_snapshot", 1.0))
            return {
                "manifest": result.manifest,
                "progress_events": progress_events,
                "output_path": output_dir / "dataset_remove.json",
            }

        if operation == "generate_synthetic_dataset":
            synthetic_progress: list[tuple[str, float]] = []

            def record_synthetic_progress(stage: str, pct: float) -> None:
                synthetic_progress.append((stage, pct))

            synthetic_request = _synthetic_dataset_request_from_ext(
                ext,
                job_id=job_id,
            )
            package = generate_synthetic_dataset_package(
                synthetic_request,
                jobs_root=self._jobs_root,
                output_dir=output_dir,
                progress=record_synthetic_progress,
            )
            manifest = dict(package.manifest_payload)
            manifest.setdefault("job_id", job_id)
            progress_events.extend(synthetic_progress)
            return {
                "manifest": manifest,
                "progress_events": progress_events,
                "output_path": package.output_path,
            }

        raise ModelOperationError(
            code="invalid_argument",
            message=f"Unsupported dataset operation: {operation}",
        )

    def _run_specialized_model_operation(
        self,
        *,
        operation: str,
        job_id: str,
        request: maintenance_pb2.ConvertModelRequest,
        output_dir: Path,
    ):
        if operation == "remove_derived_model":
            progress_events: list[tuple[str, float]] = []

            def record_progress(stage: str, pct: float) -> None:
                progress_events.append((stage, pct))

            result = self._run_remove_derived_model_operation(
                job_id=job_id,
                request_ext=dict(request.ext),
                output_dir=output_dir,
                progress=record_progress,
            )
            return result, progress_events

        if operation == "build_training_dataset":
            source_model = self._registry.model_catalog.get(request.source_model)
            if source_model is None:
                raise ModelOperationError(
                    code="unsupported_model_family",
                    message="Unknown source model for model operation.",
                    details={"source_model": request.source_model},
                )

            progress_events: list[tuple[str, float]] = []

            def record_progress(stage: str, pct: float) -> None:
                progress_events.append((stage, pct))

            artifact = build_training_dataset_artifact(
                dict(request.ext),
                jobs_root=self._jobs_root,
                output_dir=output_dir,
                source_model_id=source_model.model_id,
                progress=record_progress,
            )
            return (
                ModelOperationManifestResult(
                    manifest=artifact.manifest_payload,
                    manifest_path=artifact.manifest_path,
                    output_path=artifact.output_path,
                ),
                progress_events,
            )

        source_model = self._registry.model_catalog.get(request.source_model)
        if source_model is None:
            raise ModelOperationError(
                code="unsupported_model_family",
                message="Unknown source model for model operation.",
                details={"source_model": request.source_model},
            )

        progress_events: list[tuple[str, float]] = []

        def record_progress(stage: str, pct: float) -> None:
            progress_events.append((stage, pct))

        if operation == "train_lora":
            result = self._lora_training_pipeline.run(
                job_id=job_id,
                request_ext=dict(request.ext),
                source_model=source_model,
                output_dir=output_dir,
                jobs_root=self._jobs_root,
                progress=record_progress,
            )
            return result, progress_events

        result = self._adapter_activation_pipeline.run(
            job_id=job_id,
            request_ext=dict(request.ext),
            source_model=source_model,
            output_dir=output_dir,
            progress=record_progress,
        )
        return result, progress_events

    def _run_remove_derived_model_operation(
        self,
        *,
        job_id: str,
        request_ext: dict[str, str],
        output_dir: Path,
        progress,
    ) -> ModelOperationManifestResult:
        started_at = time.perf_counter()
        derived_model_id = request_ext.get("derived_model_id", "").strip()
        activation_manifest_path = (
            request_ext.get("manifest_path", "").strip()
            or request_ext.get("derived_model_manifest_path", "").strip()
            or request_ext.get("artifact_path", "").strip()
        )
        if not derived_model_id and not activation_manifest_path:
            raise ModelOperationError(
                code="invalid_argument",
                message="remove_derived_model requires derived_model_id or manifest_path.",
            )

        progress("resolve_target", 0.2)
        target = self._job_registry.resolve_derived_model_target(
            derived_model_id=derived_model_id,
            manifest_path=activation_manifest_path,
        )
        if target is None:
            raise ModelOperationError(
                code="not_found",
                message="Derived model target was not found.",
                details={
                    "derived_model_id": derived_model_id,
                    "manifest_path": activation_manifest_path,
                },
            )

        progress("unload_runtime", 0.55)
        unloaded_handles: list[str] = []
        for handle in list(self._registry.list_loaded_models()):
            loaded_model = self._registry.get_loaded_model(handle)
            if loaded_model is None:
                continue
            if loaded_model.spec.model_id != target["derived_model_id"]:
                continue
            if self._registry.unload_model(handle):
                unloaded_handles.append(handle)

        progress("remove_artifacts", 0.8)
        removed_paths: list[str] = []
        managed_dir = Path(target["activation_manifest_path"]).expanduser().resolve().parent
        if managed_dir.exists():
            shutil.rmtree(managed_dir)
            removed_paths.append(str(managed_dir))

        manifest = {
            "schema_version": "melix.derived_model_removal.v1",
            "job_id": job_id,
            "operation": "remove_derived_model",
            "source_model": target["source_model"],
            "derived_model_id": target["derived_model_id"],
            "derived_model_alias": target["derived_model_alias"],
            "activation_mode": target["activation_mode"],
            "activation_job_id": target["activation_job_id"],
            "activation_manifest_path": target["activation_manifest_path"],
            "adapter_manifest_path": target["adapter_manifest_path"],
            "removed": True,
            "unloaded": bool(unloaded_handles),
            "unloaded_handles": unloaded_handles,
            "removed_paths": removed_paths,
            "remove_duration_ms": (time.perf_counter() - started_at) * 1000.0,
        }
        manifest_path = self._artifact_path("remove_derived_model", output_dir)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        progress("write_manifest", 0.95)
        return ModelOperationManifestResult(manifest=manifest, manifest_path=manifest_path)

    def _restore_derived_models_into_catalog(self) -> None:
        for manifest in self._job_registry.active_derived_model_manifests():
            self._register_derived_model_manifest(manifest)

    def _register_derived_model_manifest(self, manifest: dict[str, Any]) -> common_pb2.ModelSpec | None:
        model_spec = self._derived_model_spec_from_manifest(manifest)
        if model_spec is None:
            return None
        return self._registry.model_catalog.register_model(model_spec)

    def _derived_model_spec_from_manifest(self, manifest: dict[str, Any]) -> common_pb2.ModelSpec | None:
        derived_model_id = str(manifest.get("derived_model_id", "")).strip()
        derived_model_path = str(manifest.get("derived_model_path", "")).strip()
        source_model_id = str(manifest.get("source_model", "")).strip()
        if not derived_model_id or not derived_model_path:
            return None

        source_model = self._registry.model_catalog.get(source_model_id) if source_model_id else None
        model_spec = common_pb2.ModelSpec()
        if source_model is not None:
            model_spec.CopyFrom(source_model)

        model_spec.model_id = derived_model_id
        model_spec.model_path = derived_model_path
        model_spec.model_kind = str(manifest.get("source_model_kind", "")).strip() or model_spec.model_kind or "text"
        model_spec.revision = str(manifest.get("source_model_revision", "")).strip() or model_spec.revision or "derived"
        model_spec.tokenizer_hash = (
            str(manifest.get("source_model_tokenizer_hash", "")).strip() or model_spec.tokenizer_hash
        )
        model_spec.quant_profile_id = (
            str(manifest.get("source_model_quant_profile_id", "")).strip() or model_spec.quant_profile_id
        )
        model_spec.parser_mode = (
            str(manifest.get("source_model_parser_mode", "")).strip() or model_spec.parser_mode or "text"
        )
        model_spec.reasoning_mode = (
            str(manifest.get("source_model_reasoning_mode", "")).strip() or model_spec.reasoning_mode or "off"
        )
        try:
            resolved_max_context = int(manifest.get("source_model_max_context", 0))
        except (TypeError, ValueError):
            resolved_max_context = 0
        if resolved_max_context > 0:
            model_spec.max_context = resolved_max_context

        source_ext = manifest.get("source_model_ext")
        if isinstance(source_ext, dict):
            model_spec.ext.clear()
            for key, value in source_ext.items():
                normalized_key = str(key).strip()
                if normalized_key:
                    model_spec.ext[normalized_key] = str(value)

        model_spec.ext["melix.model_path"] = derived_model_path
        model_spec.ext["melix.model_revision"] = model_spec.revision
        model_spec.ext["melix.derived_from_adapter"] = "true"
        model_spec.ext["melix.derived_from_model_id"] = source_model_id
        model_spec.ext["melix.derived_from_model_revision"] = str(manifest.get("source_model_revision", "")).strip()
        model_spec.ext["melix.derived_model_alias"] = str(manifest.get("derived_model_alias", "")).strip()
        activation_mode = str(manifest.get("activation_mode", "")).strip()
        if activation_mode:
            model_spec.ext["melix.activation_mode"] = activation_mode
        # Compute the typed RuntimeMode enum from the canonical activation_mode
        # string — the on-disk manifest keeps the human-readable string as its
        # authoritative form, and we derive the enum at registration time so
        # runtime consumers get a strongly-typed signal without coupling the
        # JSON manifest to the proto wire encoding. Manifests written by
        # pre-enum activations simply resolve as UNSPECIFIED and fall through
        # to the ext-string path in the runtime backend.
        if activation_mode == "adapter_backed_runtime":
            model_spec.runtime_mode = common_pb2.RUNTIME_MODE_ADAPTER_BACKED
        elif activation_mode == "fused_derived_model":
            model_spec.runtime_mode = common_pb2.RUNTIME_MODE_FUSED_DERIVED_MODEL
        for manifest_key, ext_key in (
            ("adapter_manifest_path", "melix.adapter_manifest_path"),
            ("adapter_weights_path", "melix.adapter_weights_path"),
            ("adapter_set_hash", "melix.adapter_set_hash"),
            ("adapter_scope", "melix.adapter_scope"),
            ("training_surface", "melix.training_surface"),
            ("component_model_type", "melix.component_model_type"),
            ("component_family", "melix.component_family"),
            ("component_model_path", "melix.component_model_path"),
        ):
            value = str(manifest.get(manifest_key, "")).strip()
            if value:
                model_spec.ext[ext_key] = value
        for manifest_key, ext_key in (
            ("adapter_scope", "melix.lora.adapter_scope"),
            ("training_surface", "melix.lora.training_surface"),
            ("component_model_type", "melix.lora.component_model_type"),
            # Component-scoped adapters use the trainable component family for downstream
            # LoRA resolution, which may differ from the wrapper model family.
            ("component_family", "melix.lora.family_id"),
            ("component_model_path", "melix.lora.base_model_path"),
        ):
            value = str(manifest.get(manifest_key, "")).strip()
            if value:
                model_spec.ext[ext_key] = value
        return model_spec

    @staticmethod
    def _linked_quantization_metadata(
        request: maintenance_pb2.ConvertModelRequest,
    ) -> dict[str, object] | None:
        artifact_path_raw = request.ext.get("artifact_path", "") or request.source_model
        if not artifact_path_raw:
            return None
        artifact_path = Path(artifact_path_raw)
        manifest_path = artifact_path / "manifest.json" if artifact_path.is_dir() else Path(
            request.ext.get("quantization_manifest_path", "")
        )
        if not manifest_path.is_file():
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        if not isinstance(manifest, dict):
            return None
        if manifest.get("artifact_kind") != "quantized_model_bundle":
            return None
        calibration = manifest.get("calibration", {}) if isinstance(manifest.get("calibration"), dict) else {}
        compatibility = manifest.get("compatibility", {}) if isinstance(manifest.get("compatibility"), dict) else {}
        quant_profile = manifest.get("quant_profile", {}) if isinstance(manifest.get("quant_profile"), dict) else {}
        return {
            "artifact_kind": manifest.get("artifact_kind", ""),
            "artifact_path": str(artifact_path),
            "manifest_path": str(manifest_path),
            "source_model": manifest.get("source_model", ""),
            "protected_scope": manifest.get("protected_scope", ""),
            "quant_profile_id": quant_profile.get("quant_profile_id", ""),
            "calibration_sample_count": calibration.get("sample_count", 0),
            "smoke_test_passed": compatibility.get("smoke_test_passed", False),
        }

    @staticmethod
    def _bench_metrics_for_suite(suite: str) -> list[BenchMetricSpec]:
        if suite == "latency":
            return [
                BenchMetricSpec(suite=suite, name="bench.latency.p50_ms", value=31.18, unit="ms"),
                BenchMetricSpec(suite=suite, name="bench.latency.p95_ms", value=44.72, unit="ms"),
            ]
        return [
            BenchMetricSpec(suite=suite, name=f"bench.{suite}.ttft_ms", value=24.45, unit="ms"),
            BenchMetricSpec(
                suite=suite,
                name=f"bench.{suite}.tokens_per_second",
                value=47.08,
                unit="tok/s",
            ),
        ]

    def _resolve_benchmark_loaded_model(self, model_handle: str) -> BenchmarkLoadedModelResolution:
        if model_handle:
            loaded_model = self._registry.get_loaded_model(model_handle)
            if loaded_model is not None:
                rss_bytes = self._current_process_rss_bytes()
                return BenchmarkLoadedModelResolution(
                    lazy_model_handle="",
                    loaded_model=loaded_model,
                    load_rss_before_bytes=rss_bytes,
                    load_rss_after_bytes=rss_bytes,
                )

        model_id = model_handle.split("::", 1)[0] if model_handle else "melix-dev-text"
        model_spec = self._registry.model_catalog.get(model_id)
        if model_spec is None:
            raise ModelOperationError(
                code="not_found",
                message="Unknown benchmark model.",
                details={"model_id": model_id},
            )
        load_rss_before_bytes = self._current_process_rss_bytes()
        loaded_model = self._registry.load_model(model_spec)
        load_rss_after_bytes = self._current_process_rss_bytes()
        return BenchmarkLoadedModelResolution(
            lazy_model_handle=loaded_model.handle,
            loaded_model=loaded_model,
            load_rss_before_bytes=load_rss_before_bytes,
            load_rss_after_bytes=load_rss_after_bytes,
        )

    @staticmethod
    def _current_process_rss_bytes() -> int:
        statm_path = Path(f"/proc/{os.getpid()}/statm")
        try:
            parts = statm_path.read_text(encoding="ascii").split()
            if len(parts) >= 2:
                resident_pages = int(parts[1])
                page_size = int(os.sysconf("SC_PAGE_SIZE"))
                return max(resident_pages * page_size, 0)
        except (OSError, ValueError):
            pass
        try:
            output = subprocess.check_output(
                ["ps", "-o", "rss=", "-p", str(os.getpid())],
                text=True,
                timeout=1.0,
            )
            rss_kib = int(output.strip().splitlines()[-1])
            return max(rss_kib * 1024, 0)
        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
            pass
        try:
            rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        except Exception:
            return 0
        if rss <= 0:
            return 0
        if sys.platform == "darwin":
            return rss
        return rss * 1024

    def _model_memory_summary(
        self,
        *,
        loaded_model,
        load_triggered_by_run: bool = False,
        load_rss_before_bytes: int = 0,
        load_rss_after_bytes: int = 0,
    ) -> dict[str, object]:
        stats = self._registry.runtime_stats()
        runtime = getattr(loaded_model, "runtime", None)
        spec = getattr(loaded_model, "spec", None)
        return {
            "runtime_model_handle": str(getattr(loaded_model, "handle", "") or ""),
            "runtime_model_id": str(getattr(spec, "model_id", "") or ""),
            "runtime_kind": str(getattr(loaded_model, "runtime_kind", "") or ""),
            "runtime_name": str(getattr(runtime, "runtime_name", "") or ""),
            "loaded_model_estimated_resident_bytes": int(
                getattr(loaded_model, "estimated_resident_bytes", 0) or 0
            ),
            "runtime_stats_resident_bytes": int(getattr(stats, "resident_bytes", 0) or 0),
            "runtime_stats_model_resident_bytes": int(getattr(stats, "model_resident_bytes", 0) or 0),
            "runtime_stats_cache_resident_bytes": int(getattr(stats, "cache_resident_bytes", 0) or 0),
            "runtime_stats_kv_cache_bytes": int(getattr(stats, "kv_cache_bytes", 0) or 0),
            "runtime_stats_memory_headroom_bytes": int(getattr(stats, "memory_headroom_bytes", 0) or 0),
            "load_triggered_by_run": bool(load_triggered_by_run),
            "load_rss_before_bytes": max(int(load_rss_before_bytes or 0), 0),
            "load_rss_after_bytes": max(int(load_rss_after_bytes or 0), 0),
            "load_rss_delta_bytes": max(
                int(load_rss_after_bytes or 0) - int(load_rss_before_bytes or 0),
                0,
            ) if load_triggered_by_run else 0,
            "measurement_scope": "worker_registry",
        }

    @staticmethod
    def _truthy_parameter(parameters: dict[str, str], key: str) -> bool:
        raw_value = parameters.get(key, parameters.get(f"melix.{key}", ""))
        return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _runtime_evidence_for_loaded_model(loaded_model) -> dict[str, str]:
        if loaded_model is None:
            return {
                "runtime_live_model": "false",
                "runtime_model_handle": "",
                "runtime_kind": "",
                "runtime_name": "",
                "runtime_model_id": "",
                "runtime_model_path": "",
                "runtime_source_kind": "",
                "runtime_source_repo": "",
            }

        spec = getattr(loaded_model, "spec", None)
        runtime = getattr(loaded_model, "runtime", None)
        runtime_name = str(getattr(runtime, "runtime_name", "") or "")
        runtime_kind = str(getattr(loaded_model, "runtime_kind", "") or "")
        model_id = str(getattr(spec, "model_id", "") or "")
        model_path = str(getattr(spec, "model_path", "") or "")
        ext = getattr(spec, "ext", {}) if spec is not None else {}
        source_kind = str(ext.get("melix.source_kind", "") if hasattr(ext, "get") else "")
        source_repo = str(
            ext.get("melix.hf_repo_id", "")
            or ext.get("melix.source_repo", "")
            or ext.get("melix.model_path", "")
            if hasattr(ext, "get")
            else ""
        )
        live_model = MaintenanceCore._runtime_name_is_live(runtime_name)
        return {
            "runtime_live_model": "true" if live_model else "false",
            "runtime_model_handle": str(getattr(loaded_model, "handle", "") or ""),
            "runtime_kind": runtime_kind,
            "runtime_name": runtime_name,
            "runtime_model_id": model_id,
            "runtime_model_path": model_path,
            "runtime_source_kind": source_kind,
            "runtime_source_repo": source_repo,
        }

    @staticmethod
    def _runtime_name_is_live(runtime_name: str) -> bool:
        normalized = runtime_name.strip().lower()
        if not normalized:
            return False
        if normalized.startswith("deterministic"):
            return False
        if "unavailable" in normalized:
            return False
        return True

    @staticmethod
    def _validate_required_live_model(runtime_evidence: dict[str, str], *, operation: str) -> None:
        if runtime_evidence.get("runtime_live_model") == "true" and runtime_evidence.get("runtime_model_handle"):
            return
        runtime_name = runtime_evidence.get("runtime_name", "") or "missing"
        model_handle = runtime_evidence.get("runtime_model_handle", "") or "missing"
        raise ModelOperationError(
            code="live_model_required",
            message=(
                f"{operation} requires a loaded live model runtime; "
                f"runtime_name={runtime_name}; model_handle={model_handle}"
            ),
            details={"runtime_name": runtime_name, "model_handle": model_handle},
        )

    @staticmethod
    def _resolved_benchmark_task_kind(
        *,
        request: maintenance_pb2.RunBenchRequest,
        parameters: dict[str, str],
        loaded_model,
    ) -> str:
        runtime_metadata = {}
        runtime_model = getattr(loaded_model, "runtime_model", None)
        if isinstance(runtime_model, dict):
            raw_metadata = runtime_model.get("metadata")
            if isinstance(raw_metadata, dict):
                runtime_metadata = {
                    str(key): str(value)
                    for key, value in raw_metadata.items()
                }
        if runtime_metadata.get("melix.vlm.execution_mode", "").strip() == "text_backed":
            return "text-generation"
        explicit = getattr(request, "task_kind", "").strip()
        if explicit:
            return explicit
        if parameters.get("benchmark_mode", "").strip().lower() == "vlm":
            return "image-text-to-text"
        model_kind = getattr(getattr(loaded_model, "spec", None), "model_kind", "").strip()
        if model_kind == "vlm":
            return "image-text-to-text"
        if model_kind == "ocr":
            return "image-to-text"
        if model_kind == "image":
            image_task_kind = getattr(getattr(loaded_model, "spec", None), "ext", {}).get(
                "melix.image.task_kind",
                "",
            ).strip()
            return image_task_kind or "text-to-image"
        return "text-generation"

    @staticmethod
    def _resolved_benchmark_matrix_task_kind(
        *,
        request: maintenance_pb2.RunBenchMatrixRequest,
        loaded_model,
    ) -> str:
        runtime_metadata = {}
        runtime_model = getattr(loaded_model, "runtime_model", None)
        if isinstance(runtime_model, dict):
            raw_metadata = runtime_model.get("metadata")
            if isinstance(raw_metadata, dict):
                runtime_metadata = {
                    str(key): str(value)
                    for key, value in raw_metadata.items()
                }
        if runtime_metadata.get("melix.vlm.execution_mode", "").strip() == "text_backed":
            return "text-generation"
        explicit = getattr(request, "task_kind", "").strip()
        if explicit:
            return explicit
        model_kind = getattr(getattr(loaded_model, "spec", None), "model_kind", "").strip()
        if model_kind == "vlm":
            return "image-text-to-text"
        if model_kind == "ocr":
            return "image-to-text"
        return "text-generation"

    @staticmethod
    def _positive_sorted_values(values, *, default: tuple[int, ...]) -> tuple[int, ...]:
        normalized_values: set[int] = set()
        for value in values:
            parsed = int(value)
            if parsed > 0:
                normalized_values.add(parsed)
        return tuple(sorted(normalized_values)) or default

    @staticmethod
    def _normalized_string_values(values, *, default: tuple[str, ...]) -> tuple[str, ...]:
        normalized_values: set[str] = set()
        for value in values:
            normalized = str(value).strip()
            if normalized:
                normalized_values.add(normalized)
        return tuple(sorted(normalized_values)) or default

    @staticmethod
    def _benchmark_matrix_request_count(
        *,
        requests: int,
        duration_seconds: int,
        repeats: int,
        concurrency_level: int,
    ) -> int:
        if requests > 0:
            return max(requests, 1)
        return max(repeats, max(duration_seconds, 1) * max(concurrency_level, 1))

    def _measure_benchmark_matrix_sample(
        self,
        *,
        loaded_model,
        suite: ResolvedBenchmarkSuite,
        case,
        task_kind: str,
        context_length: int,
        generation_length: int,
        batch_size: int,
        repeat_index: int,
        cache_profile: str,
        reasoning_mode: str,
        structured_output_mode: str,
    ) -> BenchSample:
        error_stage = "validation"
        try:
            parameters = {"max_output_tokens": str(generation_length)}
            if task_kind == "text-generation":
                prompt = ""
                if case is not None:
                    prompt = getattr(case, "prompt", "") or ""
                prompt = prompt or suite.title
                error_stage = "prompt_render"
                return self._measure_text_bench_sample(
                    loaded_model=loaded_model,
                    suite=suite,
                    prompt=prompt,
                    parameters=parameters,
                    context_length=context_length,
                    repeat_index=repeat_index,
                    batch_size=batch_size,
                    cache_profile=cache_profile,
                    reasoning_mode=reasoning_mode,
                    structured_output_mode=structured_output_mode,
                )
            if task_kind in {"image-to-text", "image-text-to-text"}:
                error_stage = "dataset_materialize"
                if case is None:
                    raise ModelOperationError(
                        code="benchmark_failed",
                        message="Benchmark matrix suite did not provide a VLM case.",
                    )
                error_stage = "prompt_render"
                sample = self._measure_vlm_bench_sample(
                    loaded_model=loaded_model,
                    suite=suite,
                    case=case,
                    parameters=parameters,
                )
                request_latency_ms = sample.request_latency_ms or sample.total_latency_ms
                decode_tokens_per_second = sample.decode_tokens_per_second
                if decode_tokens_per_second <= 0.0:
                    decode_tokens_per_second = round(
                        sample.completion_tokens / max((request_latency_ms - sample.ttft_ms) / 1_000.0, 0.001),
                        2,
                    )
                return BenchSample(
                    ttft_ms=sample.ttft_ms,
                    total_latency_ms=sample.total_latency_ms,
                    completion_tokens=sample.completion_tokens,
                    prompt_tokens=sample.prompt_tokens,
                    request_latency_ms=request_latency_ms,
                    prefill_tokens_per_second=sample.prefill_tokens_per_second,
                    decode_tokens_per_second=decode_tokens_per_second,
                    peak_memory_bytes=sample.peak_memory_bytes,
                    dataset_materialize_ms=sample.dataset_materialize_ms,
                    prompt_render_ms=sample.prompt_render_ms,
                    warmup_ms=sample.warmup_ms,
                    prefill_ms=sample.prefill_ms,
                    decode_ms=sample.decode_ms,
                    first_token_index=sample.first_token_index,
                    cache_hit=sample.cache_hit,
                    runtime_kind=sample.runtime_kind,
                    error_stage=sample.error_stage,
                    speculative_acceptance_rate=sample.speculative_acceptance_rate,
                    speculative_rollback_rate=sample.speculative_rollback_rate,
                    speculative_accepted_tokens=sample.speculative_accepted_tokens,
                    speculative_rejected_tokens=sample.speculative_rejected_tokens,
                    speculative_fallback_count=sample.speculative_fallback_count,
                    speculative_num_draft_tokens=sample.speculative_num_draft_tokens,
                    speculative_draft_model_configured=sample.speculative_draft_model_configured,
                    speculative_draft_propose_ms=sample.speculative_draft_propose_ms,
                    speculative_target_verify_ms=sample.speculative_target_verify_ms,
                    dflash_enabled=sample.dflash_enabled,
                    dflash_block_size=sample.dflash_block_size,
                    dflash_rollback_count=sample.dflash_rollback_count,
                    dflash_target_hidden_layers=sample.dflash_target_hidden_layers,
                )

            raise ModelOperationError(
                code="unsupported_task_family",
                message=f"Unsupported benchmark matrix task kind: {task_kind}",
                details={"task_kind": task_kind},
            )
        except Exception as exc:
            self._raise_benchmark_error_with_stage(exc, error_stage)

    def _measure_text_bench_metrics(
        self,
        *,
        loaded_model,
        suite: ResolvedBenchmarkSuite,
        parameters: dict[str, str],
        job_id: str,
        source_repo: str,
        task_kind: str,
        dataset_materialize_ms: float = 0.0,
    ) -> tuple[list[BenchMetricSpec], list[dict[str, object]], list[dict[str, object]], list[float]]:
        from worker.productization.benchmark_schemas import build_serving_benchmark_context_row

        context_rows: list[dict[str, object]] = []
        batch_rows: list[dict[str, object]] = []
        request_latencies: list[float] = []
        samples: list[BenchSample] = []
        model_id = (getattr(loaded_model, "handle", "") or "runtime").split("::", 1)[0]
        context_lengths = self._benchmark_context_lengths(suite=suite, parameters=parameters)
        batch_sizes = self._benchmark_batch_sizes(parameters)
        repeats = self._benchmark_repeats(parameters)
        generation_length = self._benchmark_generation_length(parameters)
        cache_profile = self._benchmark_cache_profile(parameters)
        reasoning_mode = parameters.get("reasoning_mode", "").strip()
        structured_output_mode = parameters.get("structured_output_mode", "").strip()

        for case in suite.cases:
            case_prompt = case.prompt or suite.title
            tool_run = self._agentic_tool_run_for_benchmark_case(case)
            for context_length in context_lengths:
                shaped_prompt = self._shape_benchmark_prompt(case_prompt, context_length=context_length)
                for repeat_index in range(repeats):
                    sample = self._measure_text_bench_sample(
                        loaded_model=loaded_model,
                        suite=suite,
                        prompt=shaped_prompt,
                        prompt_is_shaped=True,
                        parameters=parameters,
                        context_length=context_length,
                        repeat_index=repeat_index,
                        batch_size=1,
                        cache_profile=cache_profile,
                        reasoning_mode=reasoning_mode,
                        structured_output_mode=structured_output_mode,
                        dataset_materialize_ms=dataset_materialize_ms,
                    )
                    samples.append(sample)
                    request_latencies.append(sample.request_latency_ms)
                    context_rows.append(
                        build_serving_benchmark_context_row(
                            job_id=job_id,
                            model_id=model_id,
                            task_kind=task_kind,
                            source_repo=source_repo,
                            suite=suite.suite_id,
                            context_length=context_length,
                            generation_length=generation_length,
                            batch_size=1,
                            repeat_index=repeat_index,
                            prefill_tokens_per_second=sample.prefill_tokens_per_second,
                            decode_tokens_per_second=sample.decode_tokens_per_second,
                            ttft_ms=sample.ttft_ms,
                            request_latency_ms=sample.request_latency_ms,
                            peak_memory_bytes=sample.peak_memory_bytes,
                            speedup_vs_batch_1=1.0,
                            cache_profile=cache_profile,
                            reasoning_mode=reasoning_mode,
                            structured_output_mode=structured_output_mode,
                            dataset_materialize_ms=dataset_materialize_ms,
                            prompt_render_ms=sample.prompt_render_ms,
                            warmup_ms=sample.warmup_ms,
                            prefill_ms=sample.prefill_ms,
                            decode_ms=sample.decode_ms,
                            tokens_in=sample.prompt_tokens,
                            tokens_out=sample.completion_tokens,
                            first_token_index=sample.first_token_index,
                            cache_hit=sample.cache_hit,
                            runtime_kind=sample.runtime_kind,
                            error_stage=sample.error_stage,
                            speculative_acceptance_rate=sample.speculative_acceptance_rate,
                            speculative_rollback_rate=sample.speculative_rollback_rate,
                            speculative_accepted_tokens=sample.speculative_accepted_tokens,
                            speculative_rejected_tokens=sample.speculative_rejected_tokens,
                            speculative_fallback_count=sample.speculative_fallback_count,
                            speculative_num_draft_tokens=sample.speculative_num_draft_tokens,
                            speculative_draft_model_configured=sample.speculative_draft_model_configured,
                            speculative_draft_propose_ms=sample.speculative_draft_propose_ms,
                            speculative_target_verify_ms=sample.speculative_target_verify_ms,
                            dflash_enabled=sample.dflash_enabled,
                            dflash_block_size=sample.dflash_block_size,
                            dflash_rollback_count=sample.dflash_rollback_count,
                            dflash_target_hidden_layers=sample.dflash_target_hidden_layers,
                            **self._agentic_tool_kwargs(tool_run),
                        ).to_dict()
                    )
                    for batch_size in batch_sizes:
                        if batch_size != 1:
                            continue
                        batch_rows.append(
                            self._derive_batch_row(
                                sample=sample,
                                batch_size=batch_size,
                                context_length=context_length,
                                suite_id=suite.suite_id,
                                model_id=model_id,
                                cache_profile=cache_profile,
                                reasoning_mode=reasoning_mode,
                                structured_output_mode=structured_output_mode,
                                source_repo=source_repo,
                                generation_length=generation_length,
                                repeat_index=repeat_index,
                                job_id=job_id,
                                task_kind=task_kind,
                                tool_run=tool_run,
                            )
                        )

        if suite.suite_id == "latency":
            request_latency_p50_ms, request_latency_p95_ms = self._percentiles(request_latencies, 50.0, 95.0)
            return (
                [
                    BenchMetricSpec(
                        suite=suite.suite_id,
                        name="bench.latency.p50_ms",
                        value=request_latency_p50_ms,
                        unit="ms",
                    ),
                    BenchMetricSpec(
                        suite=suite.suite_id,
                        name="bench.latency.p95_ms",
                        value=request_latency_p95_ms,
                        unit="ms",
                    ),
                ],
                context_rows,
                batch_rows,
                request_latencies,
            )

        ttft_avg = sum(sample.ttft_ms for sample in samples) / max(len(samples), 1)
        throughput_values = [
            (sample.completion_tokens / max((sample.request_latency_ms - sample.ttft_ms) / 1_000.0, 0.001))
            for sample in samples
            if sample.completion_tokens > 0
        ]
        tokens_per_second = (
            sum(throughput_values) / len(throughput_values)
            if throughput_values
            else 0.0
        )
        return (
            [
                BenchMetricSpec(
                    suite=suite.suite_id,
                    name=f"bench.{suite.suite_id}.ttft_ms",
                    value=ttft_avg,
                    unit="ms",
                ),
                BenchMetricSpec(
                    suite=suite.suite_id,
                    name=f"bench.{suite.suite_id}.tokens_per_second",
                    value=tokens_per_second,
                    unit="tok/s",
                ),
            ],
            context_rows,
            batch_rows,
            request_latencies,
        )

    def _measure_text_bench_sample(
        self,
        *,
        loaded_model,
        suite: ResolvedBenchmarkSuite,
        prompt: str,
        parameters: dict[str, str],
        context_length: int,
        repeat_index: int,
        batch_size: int,
        cache_profile: str,
        reasoning_mode: str,
        structured_output_mode: str,
        dataset_materialize_ms: float = 0.0,
        prompt_is_shaped: bool = False,
    ) -> BenchSample:
        runtime = self._registry.runtime_for_loaded_model(loaded_model)
        shaped_prompt = prompt if prompt_is_shaped else self._shape_benchmark_prompt(prompt, context_length=context_length)
        execution_ext = self._benchmark_execution_ext(
            cache_profile=cache_profile,
            context_length=context_length,
            batch_size=batch_size,
            repeat_index=repeat_index,
            reasoning_mode=reasoning_mode,
            structured_output_mode=structured_output_mode,
        )
        warmup_ms = 0.0
        cache_hit = False
        if cache_profile not in {"cold", "warm", "partial_prefix"}:
            raise ModelOperationError(
                code="invalid_argument",
                message=f"Unsupported cache profile: {cache_profile}",
                details={"cache_profile": cache_profile, "error_stage": "validation"},
            )
        request_id = self._benchmark_request_id(
            loaded_model=loaded_model,
            suite_id=suite.suite_id,
            prompt=shaped_prompt,
            context_length=context_length,
            repeat_index=repeat_index,
            batch_size=batch_size,
            cache_profile=cache_profile,
        )
        if cache_profile == "warm":
            warmup_started_at = time.perf_counter()
            try:
                self._benchmark_warmup_text_request(
                    loaded_model=loaded_model,
                    prompt=shaped_prompt,
                    execution_ext=execution_ext,
                    request_id=f"{request_id}::warmup",
                )
            except Exception as exc:
                self._raise_benchmark_error_with_stage(exc, "warmup")
            warmup_ms = round((time.perf_counter() - warmup_started_at) * 1_000.0, 2)
            cache_hit = True
        elif cache_profile == "partial_prefix":
            partial_prefix = shaped_prompt[: max(1, len(shaped_prompt) // 2)]
            warmup_started_at = time.perf_counter()
            try:
                self._benchmark_warmup_text_request(
                    loaded_model=loaded_model,
                    prompt=partial_prefix,
                    execution_ext=execution_ext,
                    request_id=f"{request_id}::partial_prefix",
                )
            except Exception as exc:
                self._raise_benchmark_error_with_stage(exc, "warmup")
            warmup_ms = round((time.perf_counter() - warmup_started_at) * 1_000.0, 2)
            cache_hit = True

        messages = [common_pb2.ChatMessage(role="user", parts=[common_pb2.MessagePart(text=shaped_prompt)])]
        prompt_render_ms = 0.0
        render_started_at = time.perf_counter()
        try:
            rendered_prompt = runtime.render_prompt(
                messages,
                loaded_model=loaded_model.runtime_model,
                execution_ext=execution_ext,
            )
        except Exception as exc:
            self._raise_benchmark_error_with_stage(exc, "prompt_render")
        prompt_render_ms = round((time.perf_counter() - render_started_at) * 1_000.0, 2)
        rendered_prompt = self._annotated_text_benchmark_input(
            rendered_prompt,
            context_length=context_length,
            batch_size=batch_size,
        )
        cancel_event = self._registry.start_request(
            request_id=request_id,
            runtime_kind=loaded_model.runtime_kind,
        ).cancel_event
        first_token_at: float | None = None
        try:
            started_at = time.perf_counter()
            last_token_at: float | None = None
            first_token_index = 0
            completion_tokens = 0
            prompt_tokens = 0
            prompt_tps = 0.0
            generation_tps = 0.0
            peak_memory = 0.0
            speculative_acceptance_rate = 0.0
            speculative_rollback_rate = 0.0
            speculative_accepted_tokens = 0
            speculative_rejected_tokens = 0
            speculative_fallback_count = 0
            speculative_num_draft_tokens = 0
            speculative_draft_model_configured = False
            speculative_draft_propose_ms = 0.0
            speculative_target_verify_ms = 0.0
            dflash_enabled = False
            dflash_block_size = 0
            dflash_rollback_count = 0
            dflash_target_hidden_layers = 0
            sampling = common_pb2.SamplingConfig(
                temperature=0.0,
                top_p=1.0,
                top_k=1,
                max_output_tokens=self._benchmark_max_output_tokens(parameters),
            )
            for runtime_event in runtime.generate_tokens(
                loaded_model.runtime_model,
                rendered_prompt,
                sampling,
                cancel_event,
                execution_ext=execution_ext,
            ):
                text = getattr(runtime_event, "text", "")
                if not text:
                    continue
                now = time.perf_counter()
                if first_token_at is None:
                    first_token_at = now
                    first_token_index = completion_tokens + 1
                last_token_at = now
                completion_tokens = int(getattr(runtime_event, "completion_tokens", 0) or (completion_tokens + 1))
                prompt_tokens = int(getattr(runtime_event, "prompt_tokens", 0) or prompt_tokens)
                prompt_tps = float(getattr(runtime_event, "prompt_tps", 0.0) or prompt_tps)
                generation_tps = float(getattr(runtime_event, "generation_tps", 0.0) or generation_tps)
                peak_memory = float(getattr(runtime_event, "peak_memory", 0.0) or peak_memory)
                speculative_acceptance_rate = self._runtime_event_float_probe(
                    runtime_event,
                    "speculative_acceptance_rate",
                    speculative_acceptance_rate,
                )
                speculative_rollback_rate = self._runtime_event_float_probe(
                    runtime_event,
                    "speculative_rollback_rate",
                    speculative_rollback_rate,
                )
                speculative_accepted_tokens = self._runtime_event_int_probe(
                    runtime_event,
                    "speculative_accepted_tokens",
                    speculative_accepted_tokens,
                )
                speculative_rejected_tokens = self._runtime_event_int_probe(
                    runtime_event,
                    "speculative_rejected_tokens",
                    speculative_rejected_tokens,
                )
                speculative_fallback_count = self._runtime_event_int_probe(
                    runtime_event,
                    "speculative_fallback_count",
                    speculative_fallback_count,
                )
                speculative_num_draft_tokens = self._runtime_event_int_probe(
                    runtime_event,
                    "speculative_num_draft_tokens",
                    speculative_num_draft_tokens,
                )
                speculative_draft_model_configured = self._runtime_event_bool_probe(
                    runtime_event,
                    "speculative_draft_model_configured",
                    speculative_draft_model_configured,
                )
                speculative_draft_propose_ms = self._runtime_event_float_probe(
                    runtime_event,
                    "speculative_draft_propose_ms",
                    speculative_draft_propose_ms,
                )
                speculative_target_verify_ms = self._runtime_event_float_probe(
                    runtime_event,
                    "speculative_target_verify_ms",
                    speculative_target_verify_ms,
                )
                dflash_enabled = self._runtime_event_bool_probe(
                    runtime_event,
                    "dflash_enabled",
                    dflash_enabled,
                )
                dflash_block_size = self._runtime_event_int_probe(
                    runtime_event,
                    "dflash_block_size",
                    dflash_block_size,
                )
                dflash_rollback_count = self._runtime_event_int_probe(
                    runtime_event,
                    "dflash_rollback_count",
                    dflash_rollback_count,
                )
                dflash_target_hidden_layers = self._runtime_event_int_probe(
                    runtime_event,
                    "dflash_target_hidden_layers",
                    dflash_target_hidden_layers,
                )
            finished_at = time.perf_counter()
        except Exception as exc:
            self._raise_benchmark_error_with_stage(exc, "prefill" if first_token_at is None else "decode")
        finally:
            self._registry.finish_request(request_id)

        first_token_time = first_token_at or finished_at
        completed_at = last_token_at or finished_at
        request_latency_ms = round((completed_at - started_at) * 1_000.0, 2)
        ttft_ms = round((first_token_time - started_at) * 1_000.0, 2)
        if prompt_tokens <= 0:
            prompt_tokens = self._benchmark_prompt_token_count(shaped_prompt)
        if prompt_tps <= 0.0:
            prompt_tps = prompt_tokens / max(ttft_ms / 1_000.0, 0.001)
        if generation_tps <= 0.0:
            generation_tps = completion_tokens / max((request_latency_ms - ttft_ms) / 1_000.0, 0.001)
        return BenchSample(
            ttft_ms=ttft_ms,
            total_latency_ms=request_latency_ms,
            completion_tokens=completion_tokens,
            prompt_tokens=prompt_tokens,
            request_latency_ms=request_latency_ms,
            prefill_tokens_per_second=round(prompt_tps, 2),
            decode_tokens_per_second=round(generation_tps, 2),
            peak_memory_bytes=round(peak_memory, 2),
            dataset_materialize_ms=dataset_materialize_ms,
            prompt_render_ms=prompt_render_ms,
            warmup_ms=warmup_ms,
            prefill_ms=ttft_ms,
            decode_ms=round(max(request_latency_ms - ttft_ms, 0.0), 2),
            first_token_index=first_token_index,
            cache_hit=cache_hit,
            runtime_kind=getattr(loaded_model, "runtime_kind", ""),
            speculative_acceptance_rate=round(speculative_acceptance_rate, 4),
            speculative_rollback_rate=round(speculative_rollback_rate, 4),
            speculative_accepted_tokens=speculative_accepted_tokens,
            speculative_rejected_tokens=speculative_rejected_tokens,
            speculative_fallback_count=speculative_fallback_count,
            speculative_num_draft_tokens=speculative_num_draft_tokens,
            speculative_draft_model_configured=speculative_draft_model_configured,
            speculative_draft_propose_ms=round(speculative_draft_propose_ms, 2),
            speculative_target_verify_ms=round(speculative_target_verify_ms, 2),
            dflash_enabled=dflash_enabled,
            dflash_block_size=dflash_block_size,
            dflash_rollback_count=dflash_rollback_count,
            dflash_target_hidden_layers=dflash_target_hidden_layers,
        )

    @staticmethod
    def _agentic_tool_run_for_benchmark_case(case: Any | None):
        tool_calls = getattr(case, "tool_calls", ()) if case is not None else ()
        if not isinstance(tool_calls, (list, tuple)) or not tool_calls:
            return None
        fixture_context = getattr(case, "tool_fixture_context", {}) or {}
        return execute_agentic_tool_calls(
            list(tool_calls),
            fixture_context=fixture_context if isinstance(fixture_context, dict) else {},
        )

    @staticmethod
    def _agentic_tool_kwargs(tool_run: Any | None) -> dict[str, object]:
        if tool_run is None:
            return {}
        return {
            "agentic_tool_registry": tool_run.registry_receipt,
            "agentic_tool_calls": tuple(dict(call) for call in tool_run.tool_calls),
            "agentic_tool_observations": tuple(
                dict(observation) for observation in tool_run.observations
            ),
            "agentic_tool_metrics": dict(tool_run.metrics),
        }

    @staticmethod
    def _benchmark_error_stage(exc: Exception, default_stage: str = "runtime") -> str:
        stage = getattr(exc, "error_stage", "") or getattr(exc, "details", {}).get("error_stage", "")
        normalized = str(stage).strip()
        if normalized in _BENCHMARK_ERROR_STAGES:
            return normalized
        return default_stage

    @staticmethod
    def _raise_benchmark_error_with_stage(exc: Exception, error_stage: str) -> NoReturn:
        stage = error_stage if error_stage in _BENCHMARK_ERROR_STAGES else "runtime"
        if not getattr(exc, "error_stage", ""):
            setattr(exc, "error_stage", stage)
        if isinstance(exc, ModelOperationError):
            exc.details.setdefault("error_stage", stage)
        raise exc

    @staticmethod
    def _runtime_event_float_probe(runtime_event: object, field_name: str, current: float) -> float:
        value = getattr(runtime_event, field_name, None)
        if value is None:
            return current
        try:
            return float(value)
        except (TypeError, ValueError):
            return current

    @staticmethod
    def _runtime_event_int_probe(runtime_event: object, field_name: str, current: int) -> int:
        value = getattr(runtime_event, field_name, None)
        if value is None:
            return current
        try:
            return int(value)
        except (TypeError, ValueError):
            return current

    @staticmethod
    def _runtime_event_bool_probe(runtime_event: object, field_name: str, current: bool) -> bool:
        value = getattr(runtime_event, field_name, None)
        if value is None:
            return current
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @staticmethod
    def _annotated_text_benchmark_input(
        rendered_prompt: str | PreparedVisionRequest,
        *,
        context_length: int,
        batch_size: int,
    ) -> str | PreparedVisionRequest:
        benchmark_suffix = f"\n\n[context_length={context_length};batch_size={batch_size}]"
        if isinstance(rendered_prompt, PreparedVisionRequest):
            return PreparedVisionRequest(
                prompt_text=f"{rendered_prompt.prompt_text}{benchmark_suffix}",
                images=list(rendered_prompt.images),
                videos=list(rendered_prompt.videos),
                video_frame_policies=list(rendered_prompt.video_frame_policies),
                preprocess_latency_ms=rendered_prompt.preprocess_latency_ms,
                preprocess_input_bytes=rendered_prompt.preprocess_input_bytes,
                preprocess_peak_memory_bytes=rendered_prompt.preprocess_peak_memory_bytes,
                prompt_hash_hex=rendered_prompt.prompt_hash_hex,
                multimodal_hash_hex=rendered_prompt.multimodal_hash_hex,
            )
        return f"{rendered_prompt}{benchmark_suffix}"

    def _measure_vlm_bench_metrics(
        self,
        *,
        loaded_model,
        suite: ResolvedBenchmarkSuite,
        parameters: dict[str, str],
    ) -> list[BenchMetricSpec]:
        samples = [
            self._measure_vlm_bench_sample(
                loaded_model=loaded_model,
                suite=suite,
                case=case,
                parameters=parameters,
            )
            for case in suite.cases
        ]
        fast_path_metrics = self._vlm_fast_path_bench_metrics(
            suite_id=suite.suite_id,
            samples=samples,
        )
        if suite.suite_id == "latency":
            total_latencies = [sample.total_latency_ms for sample in samples]
            image_p50_ms, image_p95_ms = self._percentiles(total_latencies, 50.0, 95.0)
            return [
                BenchMetricSpec(
                    suite=suite.suite_id,
                    name="bench.latency.image_p50_ms",
                    value=image_p50_ms,
                    unit="ms",
                ),
                BenchMetricSpec(
                    suite=suite.suite_id,
                    name="bench.latency.image_p95_ms",
                    value=image_p95_ms,
                    unit="ms",
                ),
            ] + fast_path_metrics

        ttft_avg = sum(sample.ttft_ms for sample in samples) / max(len(samples), 1)
        throughput_values = [
            (sample.completion_tokens / max((sample.total_latency_ms - sample.ttft_ms) / 1_000.0, 0.001))
            for sample in samples
            if sample.completion_tokens > 0
        ]
        tokens_per_second = sum(throughput_values) / max(len(throughput_values), 1)
        return [
            BenchMetricSpec(
                suite=suite.suite_id,
                name=f"bench.{suite.suite_id}.image_ttft_ms",
                value=ttft_avg,
                unit="ms",
            ),
            BenchMetricSpec(
                suite=suite.suite_id,
                name=f"bench.{suite.suite_id}.vlm_tokens_per_second",
                value=tokens_per_second,
                unit="tok/s",
            ),
        ] + fast_path_metrics

    def _measure_vlm_bench_sample(
        self,
        *,
        loaded_model,
        suite: ResolvedBenchmarkSuite,
        case,
        parameters: dict[str, str],
    ) -> BenchSample:
        runtime = self._registry.runtime_for_loaded_model(loaded_model)
        parts = [
            common_pb2.MessagePart(
                image_uri=image_uri,
                media=common_pb2.MediaMetadata(
                    media_type=common_pb2.MEDIA_TYPE_IMAGE,
                    source_kind=common_pb2.MEDIA_SOURCE_URI,
                    filename=Path(image_uri).name,
                ),
            )
            for image_uri in case.image_uris
        ]
        if case.prompt:
            parts.insert(0, common_pb2.MessagePart(text=case.prompt))
        messages = [common_pb2.ChatMessage(role="user", parts=parts)]
        prompt_render_ms = 0.0
        render_started_at = time.perf_counter()
        try:
            prepared = runtime.render_prompt(
                messages,
                loaded_model=loaded_model.runtime_model,
                execution_ext={},
            )
        except Exception as exc:
            self._raise_benchmark_error_with_stage(exc, "prompt_render")
        prompt_render_ms = round((time.perf_counter() - render_started_at) * 1_000.0, 2)
        request_id = f"bench-{loaded_model.handle}-{suite.suite_id}-{abs(hash((case.prompt, case.image_uris)))}"
        cancel_event = self._registry.start_request(
            request_id=request_id,
            runtime_kind=loaded_model.runtime_kind,
        ).cancel_event
        first_token_at: float | None = None
        try:
            started_at = time.perf_counter()
            last_token_at: float | None = None
            first_token_index = 0
            completion_tokens = 0
            sampling = common_pb2.SamplingConfig(
                temperature=0.0,
                top_p=1.0,
                top_k=1,
                max_output_tokens=self._benchmark_max_output_tokens(parameters),
            )
            for runtime_event in runtime.generate_tokens(
                loaded_model.runtime_model,
                prepared,
                sampling,
                cancel_event,
                execution_ext={},
            ):
                text = getattr(runtime_event, "text", "")
                if not text:
                    continue
                now = time.perf_counter()
                if first_token_at is None:
                    first_token_at = now
                    first_token_index = completion_tokens + 1
                last_token_at = now
                completion_tokens = int(getattr(runtime_event, "completion_tokens", 0) or (completion_tokens + 1))
            finished_at = time.perf_counter()
        except Exception as exc:
            self._raise_benchmark_error_with_stage(exc, "prefill" if first_token_at is None else "decode")
        finally:
            self._registry.finish_request(request_id)

        first_token_time = first_token_at or finished_at
        completed_at = last_token_at or finished_at
        ttft_ms = round((first_token_time - started_at) * 1_000.0, 2)
        total_latency_ms = round((completed_at - started_at) * 1_000.0, 2)
        probe = runtime.last_probe_snapshot() if hasattr(runtime, "last_probe_snapshot") else None
        if probe is None:
            logger.debug(
                "VLM benchmark sample completed without a fast-path probe; "
                "using not-reported sentinel values."
            )
        return BenchSample(
            ttft_ms=ttft_ms,
            total_latency_ms=total_latency_ms,
            completion_tokens=completion_tokens,
            request_latency_ms=total_latency_ms,
            prompt_render_ms=prompt_render_ms,
            prefill_ms=ttft_ms,
            decode_ms=round(max(total_latency_ms - ttft_ms, 0.0), 2),
            first_token_index=first_token_index,
            runtime_kind=getattr(loaded_model, "runtime_kind", ""),
            image_feature_cache_hits=int(
                (getattr(probe, "image_feature_cache_hits", 0) or 0)
                if probe is not None
                else -1
            ),
            image_feature_cache_misses=int(
                (getattr(probe, "image_feature_cache_misses", 0) or 0)
                if probe is not None
                else -1
            ),
            multimodal_decode_mode=str(
                getattr(probe, "multimodal_decode_mode", "baseline")
                if probe is not None
                else "not_reported"
            ),
            multimodal_fallback_reason=str(
                (
                    getattr(probe, "multimodal_fallback_reason", "not_reported")
                    if probe is not None
                    else "not_reported"
                )
            ),
            multimodal_decode_sync_mode=str(
                getattr(probe, "multimodal_decode_sync_mode", "baseline")
                if probe is not None
                else "not_reported"
            ),
            multi_image_scatter_mode=str(
                getattr(probe, "multi_image_scatter_mode", "none")
                if probe is not None
                else "not_reported"
            ),
            quantized_load_mode=str(
                getattr(probe, "quantized_load_mode", "fallback")
                if probe is not None
                else "not_reported"
            ),
            quantized_load_fallback_reason=str(
                (
                    getattr(probe, "quantized_load_fallback_reason", "not_reported")
                    if probe is not None
                    else "not_reported"
                )
            ),
        )

    @staticmethod
    def _vlm_fast_path_bench_metrics(
        *,
        suite_id: str,
        samples: list[BenchSample],
    ) -> list[BenchMetricSpec]:
        if not samples:
            return []
        return [
            BenchMetricSpec(
                suite=suite_id,
                name=f"bench.{suite_id}.image_feature_cache_hits",
                value=float(
                    sum(
                        MaintenanceCore._reported_cache_count(sample.image_feature_cache_hits)
                        for sample in samples
                    )
                ),
                unit="count",
            ),
            BenchMetricSpec(
                suite=suite_id,
                name=f"bench.{suite_id}.image_feature_cache_misses",
                value=float(
                    sum(
                        MaintenanceCore._reported_cache_count(sample.image_feature_cache_misses)
                        for sample in samples
                    )
                ),
                unit="count",
            ),
            BenchMetricSpec(
                suite=suite_id,
                name=f"bench.{suite_id}.multimodal_decode_mode",
                value=MaintenanceCore._categorical_metric_code_for_samples(
                    samples,
                    "multimodal_decode_mode",
                    {
                        "baseline": 0.0,
                        "single_stream": 1.0,
                        "image_cache_reuse": 2.0,
                        "native_quantized": 3.0,
                        "fallback": 4.0,
                        "mixed": 5.0,
                        "text_only_step": 6.0,
                        "text_only_batch_generator": 7.0,
                    },
                ),
                unit="code",
            ),
            BenchMetricSpec(
                suite=suite_id,
                name=f"bench.{suite_id}.multimodal_fallback_reason",
                value=MaintenanceCore._categorical_metric_code_for_samples(
                    samples,
                    "multimodal_fallback_reason",
                    {
                        "": 0.0,
                        "not_reported": 0.0,
                        "no_media": 1.0,
                        "text_backed_no_vision_weights": 2.0,
                        "unsupported_family": 3.0,
                        "video_fast_path_unimplemented": 4.0,
                        "mixed": 5.0,
                        "text_only_batch_generator_not_enabled": 6.0,
                        "media_inputs_present": 7.0,
                        "isolated_detokenizer_unavailable": 8.0,
                        "non_greedy_sampling": 9.0,
                    },
                ),
                unit="code",
            ),
            BenchMetricSpec(
                suite=suite_id,
                name=f"bench.{suite_id}.multimodal_decode_sync_mode",
                value=MaintenanceCore._categorical_metric_code_for_samples(
                    samples,
                    "multimodal_decode_sync_mode",
                    {
                        "baseline": 0.0,
                        "executor_stream": 1.0,
                        "mixed": 2.0,
                        "executor_step": 3.0,
                        "executor_batch_generator": 4.0,
                    },
                ),
                unit="code",
            ),
            BenchMetricSpec(
                suite=suite_id,
                name=f"bench.{suite_id}.multi_image_scatter_mode",
                value=MaintenanceCore._categorical_metric_code_for_samples(
                    samples,
                    "multi_image_scatter_mode",
                    {
                        "none": 0.0,
                        "per_sample": 1.0,
                        "mixed": 2.0,
                    },
                ),
                unit="code",
            ),
            BenchMetricSpec(
                suite=suite_id,
                name=f"bench.{suite_id}.quantized_load_mode",
                value=MaintenanceCore._categorical_metric_code_for_samples(
                    samples,
                    "quantized_load_mode",
                    {
                        "fallback": 0.0,
                        "native_quantized": 1.0,
                        "mixed": 2.0,
                    },
                ),
                unit="code",
            ),
            BenchMetricSpec(
                suite=suite_id,
                name=f"bench.{suite_id}.quantized_load_fallback_reason",
                value=MaintenanceCore._categorical_metric_code_for_samples(
                    samples,
                    "quantized_load_fallback_reason",
                    {
                        "": 0.0,
                        "not_reported": 0.0,
                        "not_quantized": 1.0,
                        "unsupported_quant_profile": 2.0,
                        "text_backed_no_vision_weights": 3.0,
                        "unsupported_family": 4.0,
                        "mixed": 5.0,
                    },
                ),
                unit="code",
            ),
        ]

    @staticmethod
    def _categorical_metric_code(value: str, mapping: dict[str, float]) -> float:
        mapped_value = mapping.get(value)
        if mapped_value is None:
            logger.warning(
                "unmapped categorical metric value; value=%r allowed_values=%s",
                value,
                sorted(mapping),
            )
            return -1.0
        return mapped_value

    @staticmethod
    def _categorical_metric_code_for_samples(
        samples: list[BenchSample],
        field_name: str,
        mapping: dict[str, float],
    ) -> float:
        values = [
            str(getattr(sample, field_name, "") or "")
            for sample in samples
        ]
        distinct_values = set(values)
        if len(distinct_values) > 1:
            return MaintenanceCore._categorical_metric_code("mixed", mapping)
        return MaintenanceCore._categorical_metric_code(next(iter(distinct_values)), mapping)

    @staticmethod
    def _reported_cache_count(value: int) -> int:
        return max(value, 0)

    def _measure_image_generation_bench_metrics(
        self,
        *,
        loaded_model,
        suite: ResolvedBenchmarkSuite,
        parameters: dict[str, str],
    ) -> list[BenchMetricSpec]:
        samples = [
            self._measure_image_generation_bench_sample(
                loaded_model=loaded_model,
                suite=suite,
                case=case,
                parameters=parameters,
            )
            for case in suite.cases
        ]
        return self._image_metrics_for_suite(suite=suite, samples=samples)

    def _measure_image_edit_bench_metrics(
        self,
        *,
        loaded_model,
        suite: ResolvedBenchmarkSuite,
        parameters: dict[str, str],
    ) -> list[BenchMetricSpec]:
        samples = [
            self._measure_image_edit_bench_sample(
                loaded_model=loaded_model,
                suite=suite,
                case=case,
                parameters=parameters,
            )
            for case in suite.cases
        ]
        return self._image_metrics_for_suite(suite=suite, samples=samples)

    def _measure_image_generation_bench_sample(
        self,
        *,
        loaded_model,
        suite: ResolvedBenchmarkSuite,
        case,
        parameters: dict[str, str],
    ) -> ImageBenchSample:
        runtime = self._registry.runtime_for_loaded_model(loaded_model)
        request = inference_pb2.ImageGenerateRequest(
            id=common_pb2.RequestIdentity(
                request_id=f"bench-{loaded_model.handle}-{suite.suite_id}-{abs(hash(case.prompt))}"
            ),
            model_handle=loaded_model.handle,
            prompt=case.prompt,
            size=parameters.get("image_size", "1024x1024"),
            n=1,
            response_format=parameters.get("response_format", "png"),
            artifact_namespace="bench",
        )
        result = runtime.generate_images(
            loaded_model.runtime_model,
            request,
            job_id=f"{request.id.request_id}::image-generate",
            images_root=self._jobs_root / "bench" / "artifacts",
            cancel_event=Event(),
        )
        probe = runtime.last_probe_snapshot()
        _ = result
        return ImageBenchSample(
            latency_ms=round(probe.job_latency_ms, 2),
            artifact_publish_ms=round(probe.artifact_publish_ms, 2),
            output_bytes=probe.output_bytes,
        )

    def _measure_image_edit_bench_sample(
        self,
        *,
        loaded_model,
        suite: ResolvedBenchmarkSuite,
        case,
        parameters: dict[str, str],
    ) -> ImageBenchSample:
        runtime = self._registry.runtime_for_loaded_model(loaded_model)
        request = inference_pb2.ImageEditRequest(
            id=common_pb2.RequestIdentity(
                request_id=f"bench-{loaded_model.handle}-{suite.suite_id}-{abs(hash((case.prompt, case.source_image_uri)))}"
            ),
            model_handle=loaded_model.handle,
            prompt=case.prompt,
            image_uri=case.source_image_uri,
            mask_uri=case.mask_uri,
            strength=1.0,
            size=parameters.get("image_size", "1024x1024"),
            n=1,
            response_format=parameters.get("response_format", "png"),
        )
        result = runtime.edit_image(
            loaded_model.runtime_model,
            request,
            job_id=f"{request.id.request_id}::image-edit",
            images_root=self._jobs_root / "bench" / "artifacts",
            cancel_event=Event(),
        )
        probe = runtime.last_probe_snapshot()
        _ = result
        return ImageBenchSample(
            latency_ms=round(probe.job_latency_ms, 2),
            artifact_publish_ms=round(probe.artifact_publish_ms, 2),
            output_bytes=probe.output_bytes,
        )

    @staticmethod
    def _benchmark_cache_profile(parameters: dict[str, str]) -> str:
        raw_value = parameters.get("cache_profile", "").strip().lower()
        if not raw_value:
            return "cold"
        if raw_value in {"cold", "warm", "partial_prefix"}:
            return raw_value
        raise ModelOperationError(
            code="invalid_argument",
            message=f"Unsupported cache profile: {raw_value}",
            details={"cache_profile": raw_value},
        )

    @staticmethod
    def _benchmark_repeats(parameters: dict[str, str]) -> int:
        raw_value = parameters.get("repeats", "").strip()
        if not raw_value:
            return 1
        try:
            return max(1, int(raw_value))
        except ValueError:
            return 1

    @staticmethod
    def _benchmark_generation_length(parameters: dict[str, str]) -> int:
        raw_value = parameters.get("generation_length", "").strip() or parameters.get("max_output_tokens", "").strip()
        if not raw_value:
            return 8
        try:
            return max(1, int(raw_value))
        except ValueError:
            return 8

    def _benchmark_context_lengths(
        self,
        *,
        suite: ResolvedBenchmarkSuite,
        parameters: dict[str, str],
    ) -> tuple[int, ...]:
        raw_value = parameters.get("context_lengths", "").strip()
        values: list[int] = []
        if raw_value:
            for token in raw_value.split(","):
                token = token.strip()
                if not token:
                    continue
                try:
                    values.append(max(1, int(token)))
                except ValueError:
                    continue
        else:
            raw_single = parameters.get("context_length", "").strip()
            if raw_single:
                try:
                    values.append(max(1, int(raw_single)))
                except ValueError:
                    values.append(32)
            else:
                default_prompt = suite.prompt_batches[0] if suite.prompt_batches else suite.title
                values.append(max(1, len(default_prompt.split())))
        return tuple(sorted(set(values)))

    @staticmethod
    def _benchmark_batch_sizes(parameters: dict[str, str]) -> tuple[int, ...]:
        raw_value = parameters.get("batch_sizes", "").strip()
        values: list[int] = []
        if raw_value:
            for token in raw_value.split(","):
                token = token.strip()
                if not token:
                    continue
                try:
                    values.append(max(1, int(token)))
                except ValueError:
                    continue
        else:
            raw_single = parameters.get("batch_size", "").strip() or parameters.get("batch_factor", "").strip()
            if raw_single:
                try:
                    values.append(max(1, int(raw_single)))
                except ValueError:
                    values.append(1)
            else:
                values.append(1)
        return tuple(sorted(set(values)))

    def _suite_prompt_for_context(self, suite: ResolvedBenchmarkSuite, *, context_length: int) -> str:
        prompt = suite.prompt_batches[0] if suite.prompt_batches else suite.title
        return self._shape_benchmark_prompt(prompt, context_length=context_length)

    @staticmethod
    @lru_cache(maxsize=256)
    def _shape_benchmark_prompt(prompt: str, *, context_length: int) -> str:
        tokens = prompt.split()
        if not tokens:
            tokens = ["benchmark"]
        if len(tokens) >= context_length:
            shaped_tokens = tuple(tokens[:context_length])
            return ShapedBenchmarkPrompt(" ".join(shaped_tokens), shaped_tokens)
        full_repeats, remainder = divmod(context_length, len(tokens))
        shaped_tokens = tuple(tokens * full_repeats + tokens[:remainder])
        if remainder:
            return ShapedBenchmarkPrompt(" ".join(shaped_tokens), shaped_tokens)
        return ShapedBenchmarkPrompt(" ".join(shaped_tokens), shaped_tokens)

    @staticmethod
    def _benchmark_prompt_token_count(prompt: str) -> int:
        if isinstance(prompt, ShapedBenchmarkPrompt):
            return max(1, prompt.token_count)
        return max(1, len(prompt.split()))

    @staticmethod
    def _benchmark_execution_ext(
        *,
        cache_profile: str,
        context_length: int,
        batch_size: int,
        repeat_index: int,
        reasoning_mode: str,
        structured_output_mode: str,
    ) -> dict[str, str]:
        return {
            "cache_profile": cache_profile,
            "context_length": str(context_length),
            "batch_size": str(batch_size),
            "repeat_index": str(repeat_index),
            "reasoning_mode": reasoning_mode,
            "structured_output_mode": structured_output_mode,
        }

    @staticmethod
    def _benchmark_request_id(
        *,
        loaded_model,
        suite_id: str,
        prompt: str,
        context_length: int,
        repeat_index: int,
        batch_size: int,
        cache_profile: str,
    ) -> str:
        handle = getattr(loaded_model, "handle", "runtime")
        digest = hashlib.sha256(
            "|".join(
                [
                    handle,
                    suite_id,
                    prompt,
                    str(context_length),
                    str(batch_size),
                    str(repeat_index),
                    cache_profile,
                ]
            ).encode("utf-8")
        ).hexdigest()[:16]
        return f"bench-{handle}-{suite_id}-{digest}"

    def _benchmark_warmup_text_request(
        self,
        *,
        loaded_model,
        prompt: str,
        execution_ext: dict[str, str],
        request_id: str,
    ) -> None:
        runtime = self._registry.runtime_for_loaded_model(loaded_model)
        messages = [common_pb2.ChatMessage(role="user", parts=[common_pb2.MessagePart(text=prompt)])]
        rendered_prompt = runtime.render_prompt(
            messages,
            loaded_model=loaded_model.runtime_model,
            execution_ext=execution_ext,
        )
        cancel_event = self._registry.start_request(
            request_id=request_id,
            runtime_kind=loaded_model.runtime_kind,
        ).cancel_event
        try:
            sampling = common_pb2.SamplingConfig(
                temperature=0.0,
                top_p=1.0,
                top_k=1,
                max_output_tokens=1,
            )
            for _ in runtime.generate_tokens(
                loaded_model.runtime_model,
                rendered_prompt,
                sampling,
                cancel_event,
                execution_ext=execution_ext,
            ):
                pass
        finally:
            self._registry.finish_request(request_id)

    @staticmethod
    def _derive_batch_row(
        *,
        sample: BenchSample,
        batch_size: int,
        context_length: int,
        suite_id: str,
        model_id: str,
        cache_profile: str,
        reasoning_mode: str,
        structured_output_mode: str,
        source_repo: str,
        generation_length: int,
        repeat_index: int,
        job_id: str,
        task_kind: str,
        tool_run: Any | None = None,
    ) -> dict[str, object]:
        from worker.productization.benchmark_schemas import build_serving_benchmark_batch_row

        return build_serving_benchmark_batch_row(
            job_id=job_id,
            model_id=model_id,
            task_kind=task_kind,
            source_repo=source_repo,
            suite=suite_id,
            context_length=context_length,
            generation_length=generation_length,
            batch_size=batch_size,
            repeat_index=repeat_index,
            prefill_tokens_per_second=sample.prefill_tokens_per_second,
            decode_tokens_per_second=sample.decode_tokens_per_second,
            ttft_ms=sample.ttft_ms,
            request_latency_ms=sample.request_latency_ms,
            peak_memory_bytes=sample.peak_memory_bytes,
            speedup_vs_batch_1=1.0,
            cache_profile=cache_profile,
            reasoning_mode=reasoning_mode,
            structured_output_mode=structured_output_mode,
            dataset_materialize_ms=sample.dataset_materialize_ms,
            prompt_render_ms=sample.prompt_render_ms,
            warmup_ms=sample.warmup_ms,
            prefill_ms=sample.prefill_ms,
            decode_ms=sample.decode_ms,
            tokens_in=sample.prompt_tokens,
            tokens_out=sample.completion_tokens,
            first_token_index=sample.first_token_index,
            cache_hit=sample.cache_hit,
            runtime_kind=sample.runtime_kind,
            error_stage=sample.error_stage,
            speculative_acceptance_rate=sample.speculative_acceptance_rate,
            speculative_rollback_rate=sample.speculative_rollback_rate,
            speculative_accepted_tokens=sample.speculative_accepted_tokens,
            speculative_rejected_tokens=sample.speculative_rejected_tokens,
            speculative_fallback_count=sample.speculative_fallback_count,
            speculative_num_draft_tokens=sample.speculative_num_draft_tokens,
            speculative_draft_model_configured=sample.speculative_draft_model_configured,
            speculative_draft_propose_ms=sample.speculative_draft_propose_ms,
            speculative_target_verify_ms=sample.speculative_target_verify_ms,
            dflash_enabled=sample.dflash_enabled,
            dflash_block_size=sample.dflash_block_size,
            dflash_rollback_count=sample.dflash_rollback_count,
            dflash_target_hidden_layers=sample.dflash_target_hidden_layers,
            **MaintenanceCore._agentic_tool_kwargs(tool_run),
        ).to_dict()

    def _image_metrics_for_suite(
        self,
        *,
        suite: ResolvedBenchmarkSuite,
        samples: list[ImageBenchSample],
    ) -> list[BenchMetricSpec]:
        latencies = [sample.latency_ms for sample in samples]
        artifact_publish = [sample.artifact_publish_ms for sample in samples]
        output_bytes = [float(sample.output_bytes) for sample in samples]
        if suite.suite_id == "latency":
            image_job_p50_ms, image_job_p95_ms = self._percentiles(latencies, 50.0, 95.0)
            return [
                BenchMetricSpec(
                    suite=suite.suite_id,
                    name="bench.latency.image_job_p50_ms",
                    value=image_job_p50_ms,
                    unit="ms",
                ),
                BenchMetricSpec(
                    suite=suite.suite_id,
                    name="bench.latency.image_job_p95_ms",
                    value=image_job_p95_ms,
                    unit="ms",
                ),
            ]
        return [
            BenchMetricSpec(
                suite=suite.suite_id,
                name=f"bench.{suite.suite_id}.image_job_latency_ms",
                value=sum(latencies) / max(len(latencies), 1),
                unit="ms",
            ),
            BenchMetricSpec(
                suite=suite.suite_id,
                name=f"bench.{suite.suite_id}.image_artifact_publish_ms",
                value=sum(artifact_publish) / max(len(artifact_publish), 1),
                unit="ms",
            ),
            BenchMetricSpec(
                suite=suite.suite_id,
                name=f"bench.{suite.suite_id}.image_output_bytes",
                value=sum(output_bytes) / max(len(output_bytes), 1),
                unit="bytes",
            ),
        ]

    @staticmethod
    def _benchmark_max_output_tokens(parameters: dict[str, str]) -> int:
        raw_value = parameters.get("max_output_tokens", "").strip()
        if raw_value:
            try:
                return max(4, int(raw_value))
            except ValueError:
                return 8
        return 8

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float:
        if not values:
            return 0.0
        return MaintenanceCore._ordered_percentile(sorted(values), percentile)

    @staticmethod
    def _percentiles(values: list[float], *percentiles: float) -> tuple[float, ...]:
        if not percentiles:
            return ()
        if not values:
            return tuple(0.0 for _ in percentiles)
        ordered = sorted(values)
        return tuple(MaintenanceCore._ordered_percentile(ordered, percentile) for percentile in percentiles)

    @staticmethod
    def _ordered_percentile(ordered: list[float], percentile: float) -> float:
        if len(ordered) == 1:
            return round(ordered[0], 2)
        rank = (len(ordered) - 1) * max(0.0, min(percentile, 100.0)) / 100.0
        lower_index = math.floor(rank)
        upper_index = math.ceil(rank)
        lower_value = ordered[lower_index]
        upper_value = ordered[upper_index]
        if lower_index == upper_index:
            return round(lower_value, 2)
        weight = rank - lower_index
        return round(lower_value + (upper_value - lower_value) * weight, 2)

    @staticmethod
    def _mean(values: list[float]) -> float:
        if not values:
            return 0.0
        return round(sum(values) / len(values), 2)

    @staticmethod
    def _stddev(values: list[float]) -> float:
        if len(values) <= 1:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        return round(math.sqrt(variance), 2)

    @staticmethod
    def _render_bench_report(
        request: maintenance_pb2.RunBenchRequest,
        metrics: list[BenchMetricSpec],
        *,
        task_kind: str,
        parameters: dict[str, str] | None = None,
        model_memory_summary: dict[str, object] | None = None,
    ) -> str:
        parameters = parameters or {}
        model_memory_summary = model_memory_summary or {}
        lines = [
            "# Melix Bench",
            "",
            f"- model_handle: {request.model_handle or 'runtime'}",
            f"- suites: {', '.join(request.suites) if request.suites else 'smoke'}",
            f"- task_kind: {task_kind}",
            f"- source_repo: {getattr(request, 'source_repo', '').strip()}",
            f"- runtime_name: {parameters.get('runtime_name', '')}",
            f"- runtime_kind: {parameters.get('runtime_kind', '')}",
            f"- runtime_live_model: {parameters.get('runtime_live_model', '')}",
            "",
        ]
        if model_memory_summary:
            lines.extend(
                [
                    "## Model Memory",
                    "",
                    f"- runtime_model_handle: {model_memory_summary.get('runtime_model_handle', '')}",
                    f"- loaded_model_estimated_resident_bytes: {model_memory_summary.get('loaded_model_estimated_resident_bytes', 0)}",
                    f"- runtime_stats_model_resident_bytes: {model_memory_summary.get('runtime_stats_model_resident_bytes', 0)}",
                    f"- load_triggered_by_run: {model_memory_summary.get('load_triggered_by_run', False)}",
                    f"- load_rss_delta_bytes: {model_memory_summary.get('load_rss_delta_bytes', 0)}",
                    "",
                ]
            )
        for metric in metrics:
            lines.append(f"- {metric.name}: {metric.value:.2f} {metric.unit}")
        return "\n".join(lines) + "\n"
