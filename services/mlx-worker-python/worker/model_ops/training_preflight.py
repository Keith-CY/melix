from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Any

from packages.protocol.python.worker.v1 import common_pb2

from worker.model_ops.errors import ModelOperationError
from worker.model_ops.training_config import LoRATrainingConfig, normalize_training_config


TRAINABILITY_PREFLIGHT_SCHEMA_VERSION = "melix.trainability_preflight.v1"

_FULL_FINETUNE_MODES = {
    "fine_tune",
    "finetune",
    "full",
    "full_finetune",
    "full_finetuning",
}


@dataclass(frozen=True)
class TrainabilityPreflightResult:
    receipt: dict[str, Any]
    config: LoRATrainingConfig | None

    @property
    def blocked(self) -> bool:
        return self.receipt.get("status") == "blocked"


def evaluate_trainability_preflight(
    *,
    source_model: common_pb2.ModelSpec,
    request_ext: dict[str, str],
    dataset_format: str,
    response_only_supported: bool,
    sample_count: int,
    validation_sample_count: int = 0,
) -> TrainabilityPreflightResult:
    started = time.perf_counter()
    training_mode = _training_mode(request_ext)
    checks: list[dict[str, Any]] = []
    operator_errors: list[dict[str, Any]] = []
    memory_estimate_latency_ms = 0.0

    early_error = _sequence_length_error(source_model, request_ext)
    if early_error is None:
        memory_started = time.perf_counter()
        early_error = _memory_fit_error(request_ext)
        memory_estimate_latency_ms = _elapsed_ms(memory_started)
    if early_error is None:
        early_error = _quantized_full_finetune_error(source_model, training_mode)

    config: LoRATrainingConfig | None = None
    if early_error is not None:
        checks.append(_blocked_check(early_error))
        operator_errors.append(_operator_error(early_error))
    else:
        try:
            config = normalize_training_config(
                source_model=source_model,
                ext=request_ext,
                dataset_format=dataset_format,
                response_only_supported=response_only_supported,
                sample_count=sample_count,
                validation_sample_count=validation_sample_count,
            )
            checks.append(
                _passed_check(
                    code="trainability_preflight_ready",
                    message="Training configuration is supported by the local worker.",
                    remediation="No remediation is required.",
                    details={"training_mode": config.training_mode},
                )
            )
            training_mode = config.training_mode
            sample_error = _insufficient_samples_error(
                sample_count,
                dataset_contract=config.dataset_contract,
            )
            if sample_error is not None:
                checks.append(_blocked_check(sample_error))
                operator_errors.append(_operator_error(sample_error))
                config = None
        except ModelOperationError as exc:
            classified = _classify_config_error(exc)
            checks.append(_blocked_check(classified))
            operator_errors.append(_operator_error(classified))

    status = "blocked" if operator_errors else "ready"
    metrics = {
        "preflight_latency_ms": _elapsed_ms(started),
        "memory_estimate_latency_ms": memory_estimate_latency_ms,
        "unsupported_configuration_count": len(operator_errors),
        "remediation_classification_count": len(operator_errors),
        "sample_count": sample_count,
        "validation_sample_count": validation_sample_count,
    }
    receipt: dict[str, Any] = {
        "schema_version": TRAINABILITY_PREFLIGHT_SCHEMA_VERSION,
        "status": status,
        "model_id": source_model.model_id,
        "model_family": _model_family(source_model),
        "dataset_format": dataset_format,
        "training_mode": training_mode,
        "sample_count": sample_count,
        "validation_sample_count": validation_sample_count,
        "checks": checks,
        "operator_errors": operator_errors,
        "metrics": metrics,
    }
    return TrainabilityPreflightResult(receipt=receipt, config=config)


def write_trainability_preflight_receipt(
    *,
    receipt: dict[str, Any],
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / "trainability-preflight.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt_path


def require_trainability_preflight_ready(
    *,
    result: TrainabilityPreflightResult,
    receipt_path: Path,
) -> LoRATrainingConfig:
    if result.blocked:
        raise trainability_preflight_error(
            receipt=result.receipt,
            receipt_path=receipt_path,
        )
    if result.config is None:
        raise invalid_trainability_preflight_ready_error(receipt_path)
    return result.config


def trainability_preflight_error(
    *,
    receipt: dict[str, Any],
    receipt_path: Path,
) -> ModelOperationError:
    operator_errors = [
        error
        for error in receipt.get("operator_errors", [])
        if isinstance(error, dict)
    ]
    first_error = operator_errors[0] if operator_errors else {}
    error_code = str(first_error.get("code", "trainability_preflight_blocked"))
    error_message = str(
        first_error.get("operator_message", "LoRA training preflight blocked the training launch.")
    )
    error_details = {
        str(key): str(value)
        for key, value in dict(first_error.get("details", {})).items()
    }
    error_details["trainability_preflight_receipt_path"] = str(receipt_path)
    return ModelOperationError(
        code=error_code,
        message=error_message,
        retriable=bool(first_error.get("retriable", False)),
        details=error_details,
    )


def invalid_trainability_preflight_ready_error(receipt_path: Path) -> ModelOperationError:
    return ModelOperationError(
        code="trainability_preflight_invalid",
        message="LoRA training preflight returned ready without a normalized config.",
        details={"trainability_preflight_receipt_path": str(receipt_path)},
    )


def _insufficient_samples_error(
    sample_count: int,
    *,
    dataset_contract: str,
) -> ModelOperationError | None:
    if dataset_contract != "sft":
        return None
    if sample_count > 0:
        return None
    return ModelOperationError(
        code="insufficient_training_samples",
        message="LoRA training requires at least one training sample.",
        details={
            "sample_count": str(sample_count),
            "minimum_sample_count": "1",
        },
    )


def _sequence_length_error(
    source_model: common_pb2.ModelSpec,
    request_ext: dict[str, str],
) -> ModelOperationError | None:
    raw_value = request_ext.get("max_seq_length", "").strip()
    if not raw_value or source_model.max_context <= 0:
        return None
    try:
        max_seq_length = int(raw_value)
    except ValueError:
        return None
    if max_seq_length <= source_model.max_context:
        return None
    return ModelOperationError(
        code="sequence_length_exceeds_model_context",
        message="Requested max_seq_length exceeds the model context window.",
        details={
            "max_seq_length": str(max_seq_length),
            "max_context": str(source_model.max_context),
        },
    )


def _memory_fit_error(request_ext: dict[str, str]) -> ModelOperationError | None:
    if _bool_ext(request_ext.get("allow_memory_risk", "")):
        return None
    estimated = _float_ext(request_ext.get("estimated_training_memory_gb", ""))
    available = _float_ext(request_ext.get("available_memory_gb", ""))
    if estimated is None or available is None or estimated <= available:
        return None
    return ModelOperationError(
        code="training_memory_fit_failed",
        message="Estimated training memory exceeds available memory.",
        details={
            "estimated_training_memory_gb": f"{estimated:.3f}",
            "available_memory_gb": f"{available:.3f}",
        },
    )


def _quantized_full_finetune_error(
    source_model: common_pb2.ModelSpec,
    training_mode: str,
) -> ModelOperationError | None:
    if training_mode not in _FULL_FINETUNE_MODES or not _looks_quantized(source_model):
        return None
    return ModelOperationError(
        code="unsupported_full_finetune_quantized_base",
        message="Full fine-tuning is not supported for quantized base models.",
        details={"training_mode": training_mode},
    )


def _classify_config_error(exc: ModelOperationError) -> ModelOperationError:
    if exc.code == "unsupported_training_mode":
        return ModelOperationError(
            code="unsupported_training_mode",
            message=exc.message,
            retriable=exc.retriable,
            details=exc.details,
        )
    return exc


def _blocked_check(error: ModelOperationError) -> dict[str, Any]:
    return {
        "code": error.code,
        "status": "blocked",
        "severity": "error",
        "operator_message": error.message,
        "remediation": _remediation(error.code),
        "details": dict(error.details),
    }


def _passed_check(
    *,
    code: str,
    message: str,
    remediation: str,
    details: dict[str, str],
) -> dict[str, Any]:
    return {
        "code": code,
        "status": "passed",
        "severity": "info",
        "operator_message": message,
        "remediation": remediation,
        "details": details,
    }


def _operator_error(error: ModelOperationError) -> dict[str, Any]:
    return {
        "code": error.code,
        "severity": "error",
        "operator_message": error.message,
        "retriable": error.retriable,
        "remediation": _remediation(error.code),
        "details": dict(error.details),
    }


def _remediation(code: str) -> str:
    return {
        "insufficient_training_samples": "Add more accepted training samples before starting training.",
        "sequence_length_exceeds_model_context": "Lower max_seq_length or choose a model with a larger context window.",
        "training_memory_fit_failed": "Choose a smaller model, reduce sequence length or batch size, or pass allow_memory_risk after review.",
        "unsupported_training_mode": "Choose a supported Melix training mode.",
        "unsupported_full_finetune_quantized_base": "Use LoRA or QLoRA for quantized bases, or switch to an unquantized base model.",
        "unsupported_model_family": "Choose a model family with productized LoRA training hooks.",
        "unsupported_lora_target_module": "Choose supported LoRA target modules for this model family.",
        "invalid_dataset_package": "Use a dataset package whose format matches the requested training objective.",
    }.get(code, "Review the typed details and adjust the training request.")


def _training_mode(request_ext: dict[str, str]) -> str:
    return request_ext.get("training_mode", "lora").strip().lower() or "lora"


def _model_family(source_model: common_pb2.ModelSpec) -> str:
    return (
        source_model.ext.get("melix.lora.family_id", "").strip()
        or source_model.ext.get("text_family_id", "").strip()
        or source_model.ext.get("melix.component.text_backbone.family_id", "").strip()
        or "unknown"
    )


def _looks_quantized(source_model: common_pb2.ModelSpec) -> bool:
    if source_model.quant_profile_id.strip():
        return True
    for key in ("melix.quantization.method", "quantization_method"):
        if source_model.ext.get(key, "").strip():
            return True
    searchable = " ".join(
        [
            source_model.model_id.lower(),
            source_model.model_path.lower(),
            source_model.revision.lower(),
        ]
    )
    return any(token in searchable for token in ("4bit", "8bit", "q4", "q8", "optiq"))


def _float_ext(raw_value: str) -> float | None:
    raw_value = raw_value.strip()
    if not raw_value:
        return None
    try:
        return float(raw_value)
    except ValueError:
        return None


def _bool_ext(raw_value: str) -> bool:
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 3)
