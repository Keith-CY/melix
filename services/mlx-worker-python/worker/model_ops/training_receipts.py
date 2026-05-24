from __future__ import annotations

from pathlib import Path
from typing import Callable
from typing import Any


IntValue = Callable[[str, int, int, str], int]
FloatValue = Callable[[str, float, float, str], float]
BoolValue = Callable[[str, bool], bool]


def build_training_planner_receipt(
    *,
    ext: dict[str, str],
    training_mode: str,
    quantization_mode: str,
    batch_size: int,
    gradient_accumulation: int,
    max_seq_length: int,
    chunked_training: bool,
    chunk_size: int,
    gradient_checkpointing: bool,
    validation_sample_count: int,
    int_value: IntValue,
    float_value: FloatValue,
    bool_value: BoolValue,
) -> dict[str, object]:
    token_budget_unit = chunk_size if chunked_training else max_seq_length
    batching_strategy = "micro_batch"
    if gradient_accumulation > 1:
        batching_strategy = "micro_batch_accumulation"
    if chunked_training:
        batching_strategy = f"chunked_{batching_strategy}"

    packing_mode = ext.get("packing_mode", "").strip().lower() or "none"
    kernel_policy = ext.get("kernel_policy", "").strip().lower()
    if not kernel_policy:
        kernel_policy = "quantized_mlx" if quantization_mode == "quantized_base" else "mlx"

    metric_for_best_model = ext.get("metric_for_best_model", "").strip()
    if not metric_for_best_model:
        metric_for_best_model = "validation_loss" if validation_sample_count > 0 else "loss_best"

    return {
        "batching_strategy": batching_strategy,
        "cutoff_len": max_seq_length,
        "micro_batch_size": batch_size,
        "effective_token_budget": batch_size * gradient_accumulation * token_budget_unit,
        "packing_mode": packing_mode,
        "media_counts": {
            "audio": media_count(ext, "media_audio_count", int_value=int_value),
            "image": media_count(ext, "media_image_count", int_value=int_value),
            "video": media_count(ext, "media_video_count", int_value=int_value),
        },
        "kernel_policy": kernel_policy,
        "expected_peak_memory_class": expected_peak_memory_class(
            batch_size=batch_size,
            gradient_accumulation=gradient_accumulation,
            token_budget_unit=token_budget_unit,
            training_mode=training_mode,
        ),
        "profile_artifact_path": ext.get("profile_artifact_path", "").strip(),
        "compiled_step_enabled": bool_value(
            ext.get("compiled_step", "") or ext.get("compiled_step_enabled", ""),
            False,
        ),
        "grad_checkpoint_enabled": gradient_checkpointing,
        "attention_backend": attention_backend_receipt(ext.get("attention_backend", "")),
        "metric_for_best_model_resolved": metric_for_best_model,
        "generation_mode": ext.get("generation_mode", "").strip().lower() or "disabled",
        "final_logit_softcapping": final_logit_softcapping(
            ext.get("final_logit_softcapping", ""),
            float_value=float_value,
        ),
    }


def media_count(ext: dict[str, str], key: str, *, int_value: IntValue) -> int:
    return int_value(ext.get(key, ""), 0, 0, key)


def expected_peak_memory_class(
    *,
    batch_size: int,
    gradient_accumulation: int,
    token_budget_unit: int,
    training_mode: str,
) -> str:
    weighted_tokens = batch_size * gradient_accumulation * token_budget_unit
    if training_mode == "qlora":
        weighted_tokens = int(weighted_tokens * 0.75)
    if weighted_tokens <= 2048:
        return "low"
    if weighted_tokens <= 12288:
        return "medium"
    return "high"


def attention_backend_receipt(raw_backend: str) -> dict[str, str]:
    backend = raw_backend.strip().lower() or "mlx"
    if backend in {"mlx", "sdpa", "eager"}:
        return {"backend": backend, "status": "accepted", "reason": ""}
    return {
        "backend": backend,
        "status": "refused",
        "reason": "unsupported_training_attention_backend",
    }


def final_logit_softcapping(
    raw_value: str,
    *,
    float_value: FloatValue,
) -> float | None:
    value = raw_value.strip().lower()
    if not value or value in {"off", "none", "disabled", "false", "0"}:
        return None
    return float_value(value, 0.0, 0.0, "final_logit_softcapping")


def typed_validation_details(
    *,
    field_name: str,
    reason: str,
    received: str,
    minimum: int | float,
    include_raw_value: bool = False,
) -> dict[str, str]:
    minimum_text = format_bound_value(minimum)
    details = {
        "field": field_name,
        "reason": reason,
        "received": received,
        "minimum": minimum_text,
        "allowed_bounds": f">={minimum_text}",
        "http_status": "422",
    }
    if include_raw_value:
        details["raw_value"] = received
    return details


def format_bound_value(value: int | float) -> str:
    if isinstance(value, float) and value.is_integer():
        return f"{value:.1f}"
    return str(value)


def resolved_bounds_receipt(
    ext: dict[str, str],
    *,
    max_steps: int,
    batch_size: int,
    sample_count: int,
    num_layers: int,
    total_layer_count: int,
) -> dict[str, dict[str, object]]:
    max_steps_requested = ext.get("max_steps", "").strip()
    return {
        "max_steps": {
            "received": max_steps_requested,
            "resolved": max_steps,
            "sentinel": "no_explicit_cap" if max_steps == 0 else "",
            "allowed_bounds": "0 or >=1",
        },
        "batch_size": {
            "received": ext.get("batch_size", "").strip(),
            "resolved": batch_size,
            "allowed_bounds": f"1..{max(sample_count, 1)}",
        },
        "num_layers": {
            "received": ext.get("num_layers", "").strip(),
            "resolved": num_layers,
            "allowed_bounds": f"1..{total_layer_count}",
        },
    }


def grad_clip_policy_receipt(
    ext: dict[str, str],
    *,
    float_value: FloatValue,
) -> dict[str, object]:
    requested = (
        ext.get("grad_clip", "").strip()
        or ext.get("gradient_clip", "").strip()
        or ext.get("gradient_clip_norm", "").strip()
    )
    if not requested:
        return {
            "requested": "",
            "resolved": 0.0,
            "enabled": False,
            "source": "default",
        }
    resolved = float_value(requested, 0.0, 0.0, "grad_clip")
    return {
        "requested": requested,
        "resolved": resolved,
        "enabled": resolved > 0.0,
        "source": "request",
    }


def eval_batch_size_receipt(
    ext: dict[str, str],
    *,
    validation_sample_count: int,
    int_value: IntValue,
) -> dict[str, object]:
    requested = ext.get("eval_batch_size", "").strip()
    if requested:
        resolved = int_value(requested, 1, 1, "eval_batch_size")
        source = "request"
    else:
        resolved = 1 if validation_sample_count > 0 else 0
        source = "default"
    return {
        "requested": requested,
        "resolved": resolved,
        "source": source,
        "validation_sample_count": validation_sample_count,
    }


def scheduler_kwargs_omitted_receipt(ext: dict[str, str]) -> dict[str, object]:
    scheduler_keys = [
        key
        for key in (
            "lr_schedule",
            "scheduler",
            "scheduler_kwargs",
            "scheduler_kwargs_json",
        )
        if ext.get(key, "").strip()
    ]
    if not scheduler_keys:
        return {
            "omitted": True,
            "reason": "scheduler_not_configured",
            "keys": [],
        }
    return {
        "omitted": True,
        "reason": "mlx_lm_lora_runner_does_not_accept_scheduler_kwargs",
        "keys": scheduler_keys,
    }


def capability_gate_receipt(
    *,
    config: Any,
    dataset: Any,
    source_model: Any,
) -> dict[str, Any]:
    return {
        "adapter_family": config.adapter_family,
        "adapter_algorithm": config.adapter_algorithm,
        "backend_supported": config.backend_supported,
        "unsupported_reason": config.unsupported_reason,
        "capabilities": dict(config.adapter_capabilities),
        "training_mode": config.training_mode,
        "training_objective": config.training_objective,
        "dataset_contract": config.dataset_contract,
        "dataset_format": dataset.package.format,
        "response_only_supported": dataset.package.response_only_supported,
        "quantization_mode": config.quantization_mode,
        "base_quantization_method": config.base_quantization_method,
        "source_model_kind": source_model.model_kind,
    }


def dataset_files_resolved_receipt(
    *,
    dataset: Any,
    normalized_snapshot: Any,
) -> dict[str, str]:
    return {
        "source_manifest_path": str(dataset.package.manifest_path),
        "source_samples_path": str(dataset.package.samples_path),
        "source_valid_path": _path_if_file(dataset.package.package_path / "valid.jsonl"),
        "normalized_manifest_path": str(normalized_snapshot.manifest_path),
        "normalized_train_path": str(normalized_snapshot.train_path),
        "normalized_valid_path": (
            str(normalized_snapshot.valid_path)
            if normalized_snapshot.valid_path is not None
            else ""
        ),
    }


def _path_if_file(path: Path) -> str:
    return str(path) if path.is_file() else ""
