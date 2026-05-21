from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import time
from typing import Any, Literal

from worker.model_ops.errors import ModelOperationError
from worker.model_ops.training_dataset import _normalize_sample
from worker.productization.evaluation_final_result import (
    EvaluationFieldMapping,
    EvaluationProfileDefinition,
    _iter_serialized_samples,
)

_SUPPORTED_COLUMN_TYPES = {
    "sampler",
    "llm_text",
    "llm_structured",
    "llm_judge",
    "expression",
}
_SUPPORTED_OUTPUT_KINDS = {"training", "evaluation_final_result", "raw_jsonl"}
_SUPPORTED_TRAINING_FORMATS = {
    "chat_messages",
    "prompt_completion",
    "text_completion",
    "preference_pair",
    "prompt_candidate",
    "reward_scored",
    "calibration",
}
_SUPPORTED_EVALUATION_RESULT_KINDS = {"json", "text"}
_SECRET_FIELD_MARKERS = ("api_key", "authorization", "token", "secret", "password")
_TELEMETRY_ENV_VAR = "NEMO_TELEMETRY_ENABLED"


@dataclass(frozen=True)
class SyntheticModelProvider:
    endpoint: str
    name: str = "melix"
    provider_type: str = "openai"
    api_key: str = ""
    extra_headers: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SyntheticModelConfig:
    alias: str
    model: str
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    timeout_seconds: float | None = None
    max_parallel_requests: int | None = None
    extra_body: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SyntheticColumnSpec:
    name: str
    column_type: Literal["sampler", "llm_text", "llm_structured", "llm_judge", "expression"]
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SyntheticSeedSource:
    source_kind: Literal[
        "local_jsonl",
        "local_csv",
        "training_package",
        "evaluation_package",
        "managed_hf_snapshot",
    ]
    source_path: Path


@dataclass(frozen=True)
class SourceConstructionMetadata:
    construction_method: str
    source_bundle_id: str
    source_bundle_revision: str = ""
    source_count: int = 0
    transformation_kinds: tuple[str, ...] = ()
    excluded_leakage_field_kinds: tuple[str, ...] = ()
    split_policy: str = ""


@dataclass(frozen=True)
class SyntheticDatasetRequest:
    dataset_id: str
    dataset_name: str
    mode: Literal["preview", "create"]
    num_records: int
    output_kind: Literal["training", "evaluation_final_result", "raw_jsonl"]
    output_format: str
    model_provider: SyntheticModelProvider
    models: tuple[SyntheticModelConfig, ...]
    columns: tuple[SyntheticColumnSpec, ...]
    job_id: str = ""
    seed_source: SyntheticSeedSource | None = None
    validation_ratio: float = 0.0
    preview_count: int = 3
    random_seed: int | None = None
    data_designer_resume_mode: Literal["never", "if_possible", "always"] = "never"
    disable_data_designer_telemetry: bool = True
    source_construction: SourceConstructionMetadata | None = None


@dataclass(frozen=True)
class SyntheticDatasetPackageResult:
    package_path: Path
    manifest_path: Path
    output_path: Path
    generated_jsonl_path: Path
    data_designer_artifact_path: Path
    config_path: Path
    manifest_payload: dict[str, Any]
    row_count: int
    validation_row_count: int
    output_kind: str
    preview_only: bool


@dataclass(frozen=True)
class _DataDesignerAPI:
    DataDesigner: type[Any]
    DataDesignerConfigBuilder: type[Any]
    ModelProvider: type[Any]
    ModelConfig: type[Any]
    ChatCompletionInferenceParams: type[Any]
    DataDesignerColumnType: Any
    get_column_config_from_kwargs: Callable[..., Any] | None
    LocalFileSeedSource: type[Any] | None


def generate_synthetic_dataset_package(
    request: SyntheticDatasetRequest,
    *,
    jobs_root: Path,
    output_dir: Path,
    progress: Callable[[str, float], None] | None = None,
) -> SyntheticDatasetPackageResult:
    """Generate DataDesigner rows and normalize them into Melix dataset packages."""

    _validate_request(request)
    started = time.perf_counter()
    timing: dict[str, float] = {}
    job_id = _resolve_job_id(request)
    package_path = output_dir.expanduser().resolve()
    data_designer_dir = package_path / "data_designer"
    artifact_path = data_designer_dir / "artifacts"
    generated_jsonl_path = data_designer_dir / "generated.jsonl"
    config_path = data_designer_dir / "config.json"
    job_root = jobs_root.expanduser().resolve() / "synthetic-data" / job_id
    seed_root = job_root / "seed"

    package_path.mkdir(parents=True, exist_ok=True)
    data_designer_dir.mkdir(parents=True, exist_ok=True)
    artifact_path.mkdir(parents=True, exist_ok=True)
    job_root.mkdir(parents=True, exist_ok=True)

    _emit(progress, "load_datadesigner", 0.05)
    api = _load_data_designer_api()

    _emit(progress, "build_datadesigner_config", 0.15)
    config_started = time.perf_counter()
    builder = _build_datadesigner_config(
        request,
        api=api,
        artifact_path=artifact_path,
        seed_root=seed_root,
    )
    _write_datadesigner_config(builder, config_path)
    timing["datadesigner_config_build_ms"] = _elapsed_ms(config_started)

    _emit(progress, "generate_rows", 0.35)
    if request.mode == "preview":
        rows = _run_preview(
            request,
            api=api,
            builder=builder,
            artifact_path=artifact_path,
            timing=timing,
        )
        _write_jsonl_rows(generated_jsonl_path, rows)
    else:
        rows = _run_create(
            request,
            api=api,
            builder=builder,
            artifact_path=artifact_path,
            generated_jsonl_path=generated_jsonl_path,
            timing=timing,
        )

    _emit(progress, "normalize_rows", 0.7)
    normalize_started = time.perf_counter()
    if request.mode == "preview":
        result = _write_preview_inspection(
            request,
            rows=rows,
            package_path=package_path,
            generated_jsonl_path=generated_jsonl_path,
            artifact_path=artifact_path,
            config_path=config_path,
            timing=timing,
        )
    elif request.output_kind == "training":
        result = _write_training_package(
            request,
            rows=rows,
            package_path=package_path,
            generated_jsonl_path=generated_jsonl_path,
            artifact_path=artifact_path,
            config_path=config_path,
            timing=timing,
        )
    elif request.output_kind == "evaluation_final_result":
        result = _write_evaluation_package(
            request,
            rows=rows,
            package_path=package_path,
            generated_jsonl_path=generated_jsonl_path,
            artifact_path=artifact_path,
            config_path=config_path,
            timing=timing,
        )
    else:
        result = _write_raw_jsonl_inspection(
            request,
            rows=rows,
            package_path=package_path,
            generated_jsonl_path=generated_jsonl_path,
            artifact_path=artifact_path,
            config_path=config_path,
            timing=timing,
        )
    result.manifest_payload.setdefault("timing", {})["melix_normalize_ms"] = _elapsed_ms(normalize_started)
    result.manifest_payload["timing"]["total_elapsed_ms"] = _elapsed_ms(started)
    _rewrite_manifest(result.manifest_path, result.manifest_payload)
    _emit(progress, "complete", 1.0)
    return result


def _validate_request(request: SyntheticDatasetRequest) -> None:
    if not request.dataset_id.strip():
        raise ModelOperationError(code="invalid_synthetic_dataset_request", message="dataset_id is required.")
    if not request.dataset_name.strip():
        raise ModelOperationError(code="invalid_synthetic_dataset_request", message="dataset_name is required.")
    if request.mode not in {"preview", "create"}:
        raise ModelOperationError(
            code="invalid_synthetic_dataset_request",
            message=f"Unsupported synthetic dataset mode: {request.mode}",
            details={"mode": request.mode},
        )
    if request.num_records <= 0:
        raise ModelOperationError(
            code="invalid_synthetic_dataset_request",
            message="num_records must be greater than zero.",
            details={"num_records": str(request.num_records)},
        )
    if request.output_kind not in _SUPPORTED_OUTPUT_KINDS:
        raise ModelOperationError(
            code="unsupported_synthetic_output",
            message=f"Unsupported synthetic output kind: {request.output_kind}",
            details={"output_kind": request.output_kind},
        )
    if request.output_kind == "training" and request.output_format not in _SUPPORTED_TRAINING_FORMATS:
        raise ModelOperationError(
            code="unsupported_synthetic_output",
            message=f"Unsupported synthetic training format: {request.output_format}",
            details={"output_format": request.output_format},
        )
    if (
        request.output_kind == "evaluation_final_result"
        and request.output_format not in _SUPPORTED_EVALUATION_RESULT_KINDS
    ):
        raise ModelOperationError(
            code="unsupported_synthetic_output",
            message=f"Unsupported final-result kind: {request.output_format}",
            details={"output_format": request.output_format},
        )
    if request.output_kind == "raw_jsonl" and request.output_format != "jsonl":
        raise ModelOperationError(
            code="unsupported_synthetic_output",
            message='raw_jsonl output requires output_format="jsonl".',
            details={"output_format": request.output_format},
        )
    if not request.model_provider.endpoint.strip():
        raise ModelOperationError(
            code="invalid_synthetic_dataset_request",
            message="model_provider.endpoint is required.",
        )
    if not request.models:
        raise ModelOperationError(
            code="invalid_synthetic_dataset_request",
            message="At least one synthetic model config is required.",
        )
    aliases: set[str] = set()
    for model in request.models:
        if not model.alias.strip() or not model.model.strip():
            raise ModelOperationError(
                code="invalid_synthetic_dataset_request",
                message="Synthetic model alias and model id are required.",
            )
        if model.alias in aliases:
            raise ModelOperationError(
                code="invalid_synthetic_dataset_request",
                message="Synthetic model aliases must be unique.",
                details={"alias": model.alias},
            )
        aliases.add(model.alias)
    if not request.columns:
        raise ModelOperationError(
            code="invalid_synthetic_dataset_request",
            message="At least one synthetic column is required.",
        )
    column_names: set[str] = set()
    for column in request.columns:
        column_name = column.name.strip()
        if not column_name:
            raise ModelOperationError(
                code="invalid_synthetic_dataset_request",
                message="Synthetic column name is required.",
            )
        if column_name in column_names:
            raise ModelOperationError(
                code="invalid_synthetic_dataset_request",
                message="Synthetic column names must be unique.",
                details={"column_name": column_name},
            )
        column_names.add(column_name)
        if column.column_type not in _SUPPORTED_COLUMN_TYPES:
            raise ModelOperationError(
                code="unsupported_synthetic_column",
                message=f"Unsupported synthetic column type: {column.column_type}",
                details={"column_type": column.column_type, "column": column.name},
            )
    if not 0.0 <= request.validation_ratio < 1.0:
        raise ModelOperationError(
            code="invalid_synthetic_dataset_request",
            message="validation_ratio must be in the range [0.0, 1.0).",
            details={"validation_ratio": str(request.validation_ratio)},
        )
    if request.preview_count <= 0:
        raise ModelOperationError(
            code="invalid_synthetic_dataset_request",
            message="preview_count must be greater than zero.",
            details={"preview_count": str(request.preview_count)},
        )
    if request.source_construction is not None:
        _validate_source_construction_metadata(request.source_construction)


def _validate_source_construction_metadata(metadata: SourceConstructionMetadata) -> None:
    if not metadata.construction_method.strip():
        raise ModelOperationError(
            code="invalid_synthetic_dataset_request",
            message="source_construction.construction_method is required.",
            details={"field": "source_construction.construction_method"},
        )
    if not metadata.source_bundle_id.strip():
        raise ModelOperationError(
            code="invalid_synthetic_dataset_request",
            message="source_construction.source_bundle_id is required.",
            details={"field": "source_construction.source_bundle_id"},
        )
    if metadata.source_count < 0:
        raise ModelOperationError(
            code="invalid_synthetic_dataset_request",
            message="source_construction.source_count must be non-negative.",
            details={"field": "source_construction.source_count"},
        )


def _load_data_designer_api() -> _DataDesignerAPI:
    try:
        interface_module = importlib.import_module("data_designer.interface")
        builder_module = importlib.import_module("data_designer.config.config_builder")
        models_module = importlib.import_module("data_designer.config.models")
        column_types_module = importlib.import_module("data_designer.config.column_types")
    except ImportError as exc:
        raise ModelOperationError(
            code="missing_optional_dependency",
            message="Synthetic dataset generation requires the data-designer optional dependency.",
            details={"extra": "synthetic-data", "package": "data-designer"},
        ) from exc

    try:
        seed_source_module = importlib.import_module("data_designer.config.seed_source")
        local_file_seed_source = getattr(seed_source_module, "LocalFileSeedSource", None)
    except ImportError:
        local_file_seed_source = None

    return _DataDesignerAPI(
        DataDesigner=getattr(interface_module, "DataDesigner"),
        DataDesignerConfigBuilder=getattr(builder_module, "DataDesignerConfigBuilder"),
        ModelProvider=getattr(models_module, "ModelProvider"),
        ModelConfig=getattr(models_module, "ModelConfig"),
        ChatCompletionInferenceParams=getattr(models_module, "ChatCompletionInferenceParams"),
        DataDesignerColumnType=getattr(column_types_module, "DataDesignerColumnType"),
        get_column_config_from_kwargs=getattr(column_types_module, "get_column_config_from_kwargs", None),
        LocalFileSeedSource=local_file_seed_source,
    )


def _build_datadesigner_config(
    request: SyntheticDatasetRequest,
    *,
    api: _DataDesignerAPI,
    artifact_path: Path,
    seed_root: Path,
) -> Any:
    model_configs = []
    for model in request.models:
        inference_kwargs = _compact_dict(
            {
                "temperature": model.temperature,
                "top_p": model.top_p,
                "max_tokens": model.max_tokens,
                "timeout": model.timeout_seconds,
                "max_parallel_requests": model.max_parallel_requests,
                "extra_body": dict(model.extra_body),
            }
        )
        inference_parameters = api.ChatCompletionInferenceParams(**inference_kwargs)
        model_configs.append(
            api.ModelConfig(
                alias=model.alias,
                model=model.model,
                provider=request.model_provider.name,
                inference_parameters=inference_parameters,
            )
        )

    builder = api.DataDesignerConfigBuilder(model_configs=model_configs)
    for column in request.columns:
        _add_datadesigner_column(builder, api=api, column=column)
    if request.seed_source is not None:
        seed_source = _stage_seed_source(request.seed_source, seed_root=seed_root, api=api)
        builder.with_seed_dataset(seed_source)
    return builder


def _run_preview(
    request: SyntheticDatasetRequest,
    *,
    api: _DataDesignerAPI,
    builder: Any,
    artifact_path: Path,
    timing: dict[str, float],
) -> list[dict[str, Any]]:
    generate_started = time.perf_counter()
    with _data_designer_telemetry(request.disable_data_designer_telemetry):
        designer = _create_data_designer(
            api,
            request,
            artifact_path=artifact_path,
        )
        preview_result = designer.preview(builder, num_records=request.num_records)
    timing["datadesigner_generate_ms"] = _elapsed_ms(generate_started)
    return _rows_from_preview_result(preview_result, limit=request.num_records)


def _run_create(
    request: SyntheticDatasetRequest,
    *,
    api: _DataDesignerAPI,
    builder: Any,
    artifact_path: Path,
    generated_jsonl_path: Path,
    timing: dict[str, float],
) -> list[dict[str, Any]]:
    resume = request.data_designer_resume_mode in {"if_possible", "always"}
    generate_started = time.perf_counter()
    with _data_designer_telemetry(request.disable_data_designer_telemetry):
        designer = _create_data_designer(
            api,
            request,
            artifact_path=artifact_path,
        )
        creation_result = designer.create(
            builder,
            num_records=request.num_records,
            dataset_name=request.dataset_name,
            resume=resume,
        )
    timing["datadesigner_generate_ms"] = _elapsed_ms(generate_started)

    export_started = time.perf_counter()
    generated_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    creation_result.export(generated_jsonl_path, format="jsonl")
    timing["datadesigner_export_ms"] = _elapsed_ms(export_started)
    return list(_iter_jsonl_rows(generated_jsonl_path, error_code="invalid_datadesigner_export"))


def _create_data_designer(
    api: _DataDesignerAPI,
    request: SyntheticDatasetRequest,
    *,
    artifact_path: Path,
) -> Any:
    provider = api.ModelProvider(
        name=request.model_provider.name,
        endpoint=request.model_provider.endpoint,
        provider_type=request.model_provider.provider_type,
        api_key=request.model_provider.api_key,
        extra_headers=dict(request.model_provider.extra_headers),
    )
    return api.DataDesigner(
        model_providers=[provider],
        artifact_path=str(artifact_path),
    )


def _write_training_package(
    request: SyntheticDatasetRequest,
    *,
    rows: list[dict[str, Any]],
    package_path: Path,
    generated_jsonl_path: Path,
    artifact_path: Path,
    config_path: Path,
    timing: dict[str, float],
) -> SyntheticDatasetPackageResult:
    normalized = [_normalize_synthetic_training_row(row, request.output_format) for row in rows]
    train_rows, validation_rows = _split_validation(normalized, request.validation_ratio)
    package_write_started = time.perf_counter()
    samples_path = package_path / "samples.jsonl"
    valid_path = package_path / "valid.jsonl"
    manifest_path = package_path / "manifest.json"
    _write_jsonl_rows(samples_path, train_rows)
    if validation_rows:
        _write_jsonl_rows(valid_path, validation_rows)
    elif valid_path.exists():
        valid_path.unlink()

    manifest_payload = _base_manifest(
        request,
        rows=rows,
        generated_jsonl_path=generated_jsonl_path,
        artifact_path=artifact_path,
        config_path=config_path,
        timing=timing,
    )
    manifest_payload.update(
        {
            "schema_version": "melix.training_dataset_package.v1",
            "dataset_id": request.dataset_id,
            "format": request.output_format,
            "sample_count": len(train_rows),
            "validation_sample_count": len(validation_rows),
            "version": "synthetic",
            "build_ready": request.mode == "create",
            "preview_only": request.mode == "preview",
            "validation_strategy": "deterministic_hash_ratio" if validation_rows else "none",
            "validation_ratio": request.validation_ratio,
            "preview_count": request.preview_count,
            "preview_samples": train_rows[: request.preview_count],
            "validation_preview_samples": validation_rows[: request.preview_count],
            "response_only_supported": request.output_format in {"chat_messages", "prompt_completion"},
        }
    )
    timing["melix_package_write_ms"] = _elapsed_ms(package_write_started)
    manifest_payload["timing"] = dict(timing)
    _rewrite_manifest(manifest_path, manifest_payload)
    return SyntheticDatasetPackageResult(
        package_path=package_path,
        manifest_path=manifest_path,
        output_path=package_path,
        generated_jsonl_path=generated_jsonl_path,
        data_designer_artifact_path=artifact_path,
        config_path=config_path,
        manifest_payload=manifest_payload,
        row_count=len(train_rows),
        validation_row_count=len(validation_rows),
        output_kind=request.output_kind,
        preview_only=request.mode == "preview",
    )


def _write_evaluation_package(
    request: SyntheticDatasetRequest,
    *,
    rows: list[dict[str, Any]],
    package_path: Path,
    generated_jsonl_path: Path,
    artifact_path: Path,
    config_path: Path,
    timing: dict[str, float],
) -> SyntheticDatasetPackageResult:
    serialized_rows = _parse_and_validate_evaluation_targets(rows, result_kind=request.output_format)
    package_write_started = time.perf_counter()
    manifest_path = package_path / "manifest.json"
    samples_path = package_path / "samples.jsonl"
    profile = EvaluationProfileDefinition(
        profile_type="final_result",
        result_kind=request.output_format,
        extraction_mode="strict_full_response",
        scoring_mode="normalized_exact_match",
        threshold=1.0,
    )
    field_mapping = EvaluationFieldMapping(
        system_path="system",
        input_text_path="input",
        target_path="target",
        sample_id_path="sample_id",
    )
    _write_jsonl_rows(samples_path, _iter_serialized_evaluation_rows(serialized_rows, field_mapping))
    manifest_payload = _base_manifest(
        request,
        rows=serialized_rows,
        generated_jsonl_path=generated_jsonl_path,
        artifact_path=artifact_path,
        config_path=config_path,
        timing=timing,
    )
    manifest_payload.update(
        {
            "schema_version": "melix.evaluation_dataset_package.v2",
            "dataset_id": request.dataset_id,
            "suite_id": request.dataset_id,
            "version": "synthetic",
            "sample_count": len(serialized_rows),
            "split": "validation",
            "task_kind": "text-generation",
            "input_modalities": ["text"],
            "profile_type": profile.profile_type,
            "result_kind": profile.result_kind,
            "extraction_mode": profile.extraction_mode,
            "scoring_mode": profile.scoring_mode,
            "threshold": profile.threshold,
            "output_schema": {},
            "ignored_paths": [],
            "build_ready": request.mode == "create",
            "preview_only": request.mode == "preview",
            "field_mapping": {
                "system_path": field_mapping.system_path,
                "input_text_path": field_mapping.input_text_path,
                "target_path": field_mapping.target_path,
                "sample_id_path": field_mapping.sample_id_path,
            },
        }
    )
    timing["melix_package_write_ms"] = _elapsed_ms(package_write_started)
    manifest_payload["timing"] = dict(timing)
    _rewrite_manifest(manifest_path, manifest_payload)
    return SyntheticDatasetPackageResult(
        package_path=package_path,
        manifest_path=manifest_path,
        output_path=package_path,
        generated_jsonl_path=generated_jsonl_path,
        data_designer_artifact_path=artifact_path,
        config_path=config_path,
        manifest_payload=manifest_payload,
        row_count=len(serialized_rows),
        validation_row_count=0,
        output_kind=request.output_kind,
        preview_only=request.mode == "preview",
    )


def _write_preview_inspection(
    request: SyntheticDatasetRequest,
    *,
    rows: list[dict[str, Any]],
    package_path: Path,
    generated_jsonl_path: Path,
    artifact_path: Path,
    config_path: Path,
    timing: dict[str, float],
) -> SyntheticDatasetPackageResult:
    package_write_started = time.perf_counter()
    manifest_path = package_path / "synthetic_dataset.preview.json"
    manifest_payload = _base_manifest(
        request,
        rows=rows,
        generated_jsonl_path=generated_jsonl_path,
        artifact_path=artifact_path,
        config_path=config_path,
        timing=timing,
    )
    manifest_payload.update(
        {
            "schema_version": "melix.synthetic_dataset_preview.v1",
            "dataset_id": request.dataset_id,
            "sample_count": len(rows),
            "build_ready": False,
            "preview_only": True,
            "preview_count": request.preview_count,
            "preview_samples": rows[: request.preview_count],
        }
    )
    timing["melix_package_write_ms"] = _elapsed_ms(package_write_started)
    manifest_payload["timing"] = dict(timing)
    _rewrite_manifest(manifest_path, manifest_payload)
    _cleanup_build_ready_package_files(package_path)
    return SyntheticDatasetPackageResult(
        package_path=package_path,
        manifest_path=manifest_path,
        output_path=generated_jsonl_path,
        generated_jsonl_path=generated_jsonl_path,
        data_designer_artifact_path=artifact_path,
        config_path=config_path,
        manifest_payload=manifest_payload,
        row_count=len(rows),
        validation_row_count=0,
        output_kind=request.output_kind,
        preview_only=True,
    )


def _write_raw_jsonl_inspection(
    request: SyntheticDatasetRequest,
    *,
    rows: list[dict[str, Any]],
    package_path: Path,
    generated_jsonl_path: Path,
    artifact_path: Path,
    config_path: Path,
    timing: dict[str, float],
) -> SyntheticDatasetPackageResult:
    package_write_started = time.perf_counter()
    manifest_path = package_path / "synthetic_dataset.inspect.json"
    manifest_payload = _base_manifest(
        request,
        rows=rows,
        generated_jsonl_path=generated_jsonl_path,
        artifact_path=artifact_path,
        config_path=config_path,
        timing=timing,
    )
    manifest_payload.update(
        {
            "schema_version": "melix.synthetic_dataset_inspection.v1",
            "dataset_id": request.dataset_id,
            "sample_count": len(rows),
            "build_ready": False,
            "preview_only": True,
            "preview_count": request.preview_count,
            "preview_samples": rows[: request.preview_count],
        }
    )
    timing["melix_package_write_ms"] = _elapsed_ms(package_write_started)
    manifest_payload["timing"] = dict(timing)
    _rewrite_manifest(manifest_path, manifest_payload)
    return SyntheticDatasetPackageResult(
        package_path=package_path,
        manifest_path=manifest_path,
        output_path=generated_jsonl_path,
        generated_jsonl_path=generated_jsonl_path,
        data_designer_artifact_path=artifact_path,
        config_path=config_path,
        manifest_payload=manifest_payload,
        row_count=len(rows),
        validation_row_count=0,
        output_kind=request.output_kind,
        preview_only=True,
    )


def _cleanup_build_ready_package_files(package_path: Path) -> None:
    for filename in ("manifest.json", "samples.jsonl", "valid.jsonl"):
        path = package_path / filename
        if path.exists():
            path.unlink()


def _base_manifest(
    request: SyntheticDatasetRequest,
    *,
    rows: list[dict[str, Any]],
    generated_jsonl_path: Path,
    artifact_path: Path,
    config_path: Path,
    timing: dict[str, float],
) -> dict[str, Any]:
    manifest = {
        "source_kind": "datadesigner",
        "operation": "generate_synthetic_dataset",
        "dataset_name": request.dataset_name,
        "output_kind": request.output_kind,
        "output_format": request.output_format,
        "row_count": len(rows),
        "timing": dict(timing),
        "datadesigner": {
            "package": "data-designer",
            "config_path": str(config_path),
            "artifact_path": str(artifact_path),
            "generated_jsonl_path": str(generated_jsonl_path),
            "num_records_requested": request.num_records,
            "num_records_generated": len(rows),
            "mode": request.mode,
            "columns": [column.name for column in request.columns],
            "model_aliases": [model.alias for model in request.models],
            "provider": _redacted_provider_manifest(request.model_provider),
            "models": [
                {
                    "alias": model.alias,
                    "model": model.model,
                    "temperature": model.temperature,
                    "top_p": model.top_p,
                    "max_tokens": model.max_tokens,
                    "timeout_seconds": model.timeout_seconds,
                    "max_parallel_requests": model.max_parallel_requests,
                    "extra_body": _redact_mapping(model.extra_body),
                }
                for model in request.models
            ],
            "secret_redaction": "applied",
            "telemetry_disabled": request.disable_data_designer_telemetry,
        },
    }
    if request.source_construction is not None:
        manifest["source_construction"] = _source_construction_manifest(
            request.source_construction,
            sample_count=len(rows),
        )
    return manifest


def _normalize_synthetic_training_row(row: dict[str, Any], output_format: str) -> dict[str, Any]:
    try:
        normalized = _normalize_sample(row, format_name=output_format, max_characters_per_sample=0)
    except ModelOperationError as exc:
        raise ModelOperationError(
            code="invalid_synthetic_output_row",
            message=f"Synthetic DataDesigner row is invalid for {output_format} training output.",
            details={"format": output_format, **exc.details},
        ) from exc
    _copy_row_source_construction(normalized, row)
    return normalized


def _parse_and_validate_evaluation_targets(
    rows: list[dict[str, Any]],
    *,
    result_kind: str,
) -> list[dict[str, Any]]:
    parsed_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        parsed_row = dict(row)
        target = row.get("target")
        if result_kind == "json":
            if isinstance(target, str):
                try:
                    target = json.loads(target)
                except json.JSONDecodeError as exc:
                    raise ModelOperationError(
                        code="invalid_synthetic_output_row",
                        message="Synthetic final-result JSON target must parse as JSON.",
                        details={"row": str(index)},
                    ) from exc
            if not isinstance(target, (dict, list)):
                raise ModelOperationError(
                    code="invalid_synthetic_output_row",
                    message="Synthetic final-result JSON target must be an object or array.",
                    details={"row": str(index)},
                )
            parsed_row["target"] = target
        elif result_kind == "text":
            if str(target or "").strip() == "":
                raise ModelOperationError(
                    code="invalid_synthetic_output_row",
                    message="Synthetic final-result text target must be non-empty.",
                    details={"row": str(index)},
                )
        _validate_row_source_construction(parsed_row, row_index=index)
        parsed_rows.append(parsed_row)
    return parsed_rows


def _iter_serialized_evaluation_rows(
    rows: list[dict[str, Any]],
    field_mapping: EvaluationFieldMapping,
) -> Iterator[dict[str, Any]]:
    for row, serialized in zip(rows, _iter_serialized_samples(rows, field_mapping), strict=True):
        _copy_row_source_construction(serialized, row)
        yield serialized


def _source_construction_manifest(
    metadata: SourceConstructionMetadata,
    *,
    sample_count: int,
) -> dict[str, Any]:
    payload = {
        "schema_version": "melix.source_construction.v1",
        "construction_method": metadata.construction_method.strip(),
        "source_bundle_id": metadata.source_bundle_id.strip(),
        "source_bundle_revision": metadata.source_bundle_revision.strip(),
        "source_count": int(metadata.source_count),
        "sample_count": int(sample_count),
        "transformation_kinds": _string_list(metadata.transformation_kinds),
        "excluded_leakage_field_kinds": _string_list(metadata.excluded_leakage_field_kinds),
        "split_policy": metadata.split_policy.strip(),
    }
    return _compact_dict(payload)


def _copy_row_source_construction(target: dict[str, Any], source: Mapping[str, Any]) -> None:
    if "source_construction" not in source:
        return
    target["source_construction"] = _validated_row_source_construction(
        source["source_construction"],
    )


def _string_list(values: Iterable[Any]) -> list[str]:
    return [item for item in (str(raw).strip() for raw in values) if item]


_ROW_SOURCE_CONSTRUCTION_KEYS = (
    "source_ids",
    "source_asset_paths",
    "image_ids",
    "entity_ids",
    "transformation_kinds",
    "excluded_leakage_fields",
    "required_tool_families",
    "answer_aliases",
    "evidence_chain",
    "hop_count",
    "rewrite_id",
    "ambiguity_notes",
)


def _validate_row_source_construction(payload: dict[str, Any], *, row_index: int) -> None:
    if "source_construction" not in payload:
        return
    payload["source_construction"] = _validated_row_source_construction(
        payload["source_construction"],
        row=row_index,
    )


def _validated_row_source_construction(value: Any, *, row: int | None = None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        details = {} if row is None else {"row": str(row)}
        raise ModelOperationError(
            code="invalid_synthetic_source_construction",
            message="Synthetic source_construction metadata must be a JSON object.",
            details=details,
        )
    payload = {key: value[key] for key in _ROW_SOURCE_CONSTRUCTION_KEYS if key in value}
    _require_string_list(payload, "source_ids", row=row)
    for key in (
        "source_asset_paths",
        "image_ids",
        "entity_ids",
        "transformation_kinds",
        "excluded_leakage_fields",
        "required_tool_families",
        "answer_aliases",
    ):
        _optional_string_list(payload, key, row=row)
    if "evidence_chain" in payload and not isinstance(payload["evidence_chain"], list):
        details = {"field": "evidence_chain"}
        if row is not None:
            details["row"] = str(row)
        raise ModelOperationError(
            code="invalid_synthetic_source_construction",
            message="Synthetic source_construction evidence_chain must be an array.",
            details=details,
        )
    if "hop_count" in payload:
        try:
            hop_count = int(payload["hop_count"])
        except (TypeError, ValueError) as exc:
            details = {"field": "hop_count"}
            if row is not None:
                details["row"] = str(row)
            raise ModelOperationError(
                code="invalid_synthetic_source_construction",
                message="Synthetic source_construction hop_count must be an integer.",
                details=details,
            ) from exc
        if hop_count < 0:
            details = {"field": "hop_count"}
            if row is not None:
                details["row"] = str(row)
            raise ModelOperationError(
                code="invalid_synthetic_source_construction",
                message="Synthetic source_construction hop_count must be non-negative.",
                details=details,
            )
        payload["hop_count"] = hop_count
    if "rewrite_id" in payload:
        payload["rewrite_id"] = str(payload["rewrite_id"]).strip()
    if "ambiguity_notes" in payload:
        payload["ambiguity_notes"] = str(payload["ambiguity_notes"]).strip()
    return _compact_dict(payload)


def _require_string_list(payload: dict[str, Any], key: str, *, row: int | None) -> None:
    if key not in payload:
        details = {"field": key}
        if row is not None:
            details["row"] = str(row)
        raise ModelOperationError(
            code="invalid_synthetic_source_construction",
            message=f"Synthetic source_construction {key} is required.",
            details=details,
        )
    _optional_string_list(payload, key, row=row)
    if not payload.get(key):
        details = {"field": key}
        if row is not None:
            details["row"] = str(row)
        raise ModelOperationError(
            code="invalid_synthetic_source_construction",
            message=f"Synthetic source_construction {key} must not be empty.",
            details=details,
        )


def _optional_string_list(payload: dict[str, Any], key: str, *, row: int | None) -> None:
    if key not in payload:
        return
    value = payload[key]
    if not isinstance(value, list):
        details = {"field": key}
        if row is not None:
            details["row"] = str(row)
        raise ModelOperationError(
            code="invalid_synthetic_source_construction",
            message=f"Synthetic source_construction {key} must be an array.",
            details=details,
        )
    payload[key] = [item for item in (str(raw).strip() for raw in value) if item]


def _split_validation(
    rows: list[dict[str, Any]],
    validation_ratio: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if validation_ratio <= 0 or len(rows) < 2:
        return rows, []
    validation_count = int(round(len(rows) * validation_ratio))
    validation_count = min(max(validation_count, 1), len(rows) - 1)
    validation_indices = {
        index
        for _, index in sorted(
            (_canonical_row_hash(row), index) for index, row in enumerate(rows)
        )[:validation_count]
    }
    train_rows: list[dict[str, Any]] = []
    validation_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if index in validation_indices:
            validation_rows.append(row)
        else:
            train_rows.append(row)
    return train_rows, validation_rows


def _canonical_row_hash(row: dict[str, Any]) -> str:
    encoded = json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _stage_seed_source(seed_source: SyntheticSeedSource, *, seed_root: Path, api: _DataDesignerAPI) -> Any:
    source_path = seed_source.source_path.expanduser().resolve()
    if not source_path.exists():
        raise ModelOperationError(
            code="invalid_synthetic_seed_source",
            message="Synthetic seed source does not exist.",
            details={"source_path": str(source_path)},
        )
    seed_root.mkdir(parents=True, exist_ok=True)
    if seed_source.source_kind in {"local_jsonl", "local_csv", "managed_hf_snapshot"}:
        staged_path = seed_root / source_path.name
        if source_path.is_dir():
            if staged_path.exists():
                if staged_path.is_dir():
                    shutil.rmtree(staged_path)
                else:
                    staged_path.unlink()
            shutil.copytree(source_path, staged_path)
        else:
            if staged_path.is_dir():
                shutil.rmtree(staged_path)
            shutil.copy2(source_path, staged_path)
    elif seed_source.source_kind == "training_package":
        staged_path = seed_root / "training-package-seed.jsonl"
        _write_jsonl_rows(staged_path, _iter_training_package_seed_rows(source_path))
    elif seed_source.source_kind == "evaluation_package":
        staged_path = seed_root / "evaluation-package-seed.jsonl"
        _write_jsonl_rows(staged_path, _iter_evaluation_package_seed_rows(source_path))
    else:
        raise ModelOperationError(
            code="invalid_synthetic_seed_source",
            message=f"Unsupported synthetic seed source kind: {seed_source.source_kind}",
            details={"source_kind": seed_source.source_kind},
        )
    if api.LocalFileSeedSource is None:
        return str(staged_path)
    if hasattr(api.LocalFileSeedSource, "from_path"):
        return api.LocalFileSeedSource.from_path(staged_path)
    return api.LocalFileSeedSource(path=str(staged_path))


def _add_datadesigner_column(
    builder: Any,
    *,
    api: _DataDesignerAPI,
    column: SyntheticColumnSpec,
) -> None:
    column_type = _datadesigner_column_type(api.DataDesignerColumnType, column.column_type)
    params = dict(column.params)
    if api.get_column_config_from_kwargs is not None:
        column_config = api.get_column_config_from_kwargs(
            name=column.name,
            column_type=column_type,
            **params,
        )
        builder.add_column(column_config)
        return
    builder.add_column(
        name=column.name,
        column_type=column_type,
        **params,
    )


def _iter_training_package_seed_rows(package_path: Path) -> Iterable[dict[str, Any]]:
    samples_path = package_path / "samples.jsonl"
    if not samples_path.is_file():
        raise ModelOperationError(
            code="invalid_synthetic_seed_source",
            message="Training seed package must contain samples.jsonl.",
            details={"package_path": str(package_path)},
        )
    yield from _iter_jsonl_rows(samples_path, error_code="invalid_synthetic_seed_source")
    valid_path = package_path / "valid.jsonl"
    if valid_path.is_file():
        yield from _iter_jsonl_rows(valid_path, error_code="invalid_synthetic_seed_source")


def _iter_evaluation_package_seed_rows(package_path: Path) -> Iterable[dict[str, Any]]:
    samples_path = package_path / "samples.jsonl"
    if not samples_path.is_file():
        raise ModelOperationError(
            code="invalid_synthetic_seed_source",
            message="Evaluation seed package must contain samples.jsonl.",
            details={"package_path": str(package_path)},
        )
    for row in _iter_jsonl_rows(samples_path, error_code="invalid_synthetic_seed_source"):
        input_payload = row.get("input")
        input_text = input_payload.get("text", "") if isinstance(input_payload, dict) else ""
        yield {
            "system": row.get("system", ""),
            "input": input_text,
            "target": row.get("target"),
            "sample_id": row.get("id", ""),
        }


def _write_datadesigner_config(builder: Any, config_path: Path) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        builder.write_config(config_path)
    except Exception as exc:
        raise ModelOperationError(
            code="synthetic_config_write_failed",
            message="Unable to write DataDesigner configuration.",
            details={"config_path": str(config_path)},
        ) from exc
    _redact_json_file(config_path)


def _rows_from_preview_result(preview_result: Any, *, limit: int) -> list[dict[str, Any]]:
    if preview_result is None:
        return []
    if isinstance(preview_result, list):
        return [dict(row) for row in preview_result if isinstance(row, dict)][:limit]
    if isinstance(preview_result, tuple):
        return [dict(row) for row in preview_result if isinstance(row, dict)][:limit]
    if hasattr(preview_result, "to_dict"):
        payload = preview_result.to_dict(orient="records")
        if isinstance(payload, list):
            return [dict(row) for row in payload if isinstance(row, dict)][:limit]
    if hasattr(preview_result, "data"):
        return _rows_from_preview_result(preview_result.data, limit=limit)
    if hasattr(preview_result, "preview_results"):
        return _rows_from_preview_result(preview_result.preview_results, limit=limit)
    raise ModelOperationError(
        code="invalid_datadesigner_preview",
        message="DataDesigner preview did not return JSON-object rows.",
        details={"preview_result_type": type(preview_result).__name__},
    )


def _iter_jsonl_rows(path: Path, *, error_code: str) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ModelOperationError(
                    code=error_code,
                    message="JSONL row is not valid JSON.",
                    details={"path": str(path), "line": str(line_number)},
                ) from exc
            if not isinstance(payload, dict):
                raise ModelOperationError(
                    code=error_code,
                    message="JSONL row must be a JSON object.",
                    details={"path": str(path), "line": str(line_number)},
                )
            yield payload


def _write_jsonl_rows(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row))
            handle.write("\n")


def _rewrite_manifest(manifest_path: Path, manifest_payload: dict[str, Any]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8")


def _resolve_job_id(request: SyntheticDatasetRequest) -> str:
    if request.job_id.strip():
        return _safe_path_component(request.job_id)
    return f"{_safe_path_component(request.dataset_id)}-{int(time.time() * 1000)}"


def _safe_path_component(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in value.strip())
    return cleaned.strip(".-") or "synthetic-dataset"


def _emit(progress: Callable[[str, float], None] | None, stage: str, fraction: float) -> None:
    if progress is not None:
        progress(stage, fraction)


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 3)


def _compact_dict(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value not in (None, {}, [])}


def _redacted_provider_manifest(provider: SyntheticModelProvider) -> dict[str, Any]:
    return {
        "name": provider.name,
        "endpoint": provider.endpoint,
        "provider_type": provider.provider_type,
        "api_key": "[REDACTED]" if provider.api_key else "",
        "extra_headers": _redact_mapping(provider.extra_headers),
    }


def _redact_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in payload.items():
        lowered = str(key).lower()
        if any(marker in lowered for marker in _SECRET_FIELD_MARKERS):
            redacted[str(key)] = "[REDACTED]"
        elif isinstance(value, Mapping):
            redacted[str(key)] = _redact_mapping(value)
        elif isinstance(value, list):
            redacted[str(key)] = [
                _redact_mapping(item) if isinstance(item, Mapping) else item
                for item in value
            ]
        else:
            redacted[str(key)] = value
    return redacted


def _redact_json_file(path: Path) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    redacted = _redact_value(payload)
    path.write_text(json.dumps(redacted, indent=2) + "\n", encoding="utf-8")


def _redact_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _redact_mapping(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


def _datadesigner_column_type(data_designer_column_type: Any, column_type: str) -> Any:
    enum_name = column_type.upper()
    if hasattr(data_designer_column_type, enum_name):
        return getattr(data_designer_column_type, enum_name)
    return column_type


@contextmanager
def _data_designer_telemetry(disable: bool) -> Iterator[None]:
    previous = os.environ.get(_TELEMETRY_ENV_VAR)
    if disable:
        os.environ[_TELEMETRY_ENV_VAR] = "false"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(_TELEMETRY_ENV_VAR, None)
        else:
            os.environ[_TELEMETRY_ENV_VAR] = previous
