from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from packages.protocol.python.worker.v1 import common_pb2

from worker.model_ops.errors import ModelOperationError


@dataclass(frozen=True)
class LoRATrainingConfig:
    training_mode: str
    quantization_mode: str
    family_id: str
    rank: int
    alpha: float
    dropout: float
    target_modules: list[str]
    expanded_target_modules: list[str]
    backend_target_modules: list[str]
    selected_layer_indices: list[int]
    total_layer_count: int
    num_layers: int
    learning_rate: float
    batch_size: int
    epochs: int
    iters: int
    max_steps: int
    response_only: bool
    gradient_checkpointing: bool
    gradient_accumulation: int
    mask_prompt: bool
    max_seq_length: int
    steps_per_report: int
    steps_per_eval: int
    steps_per_save: int
    validation_strategy: str
    validation_split: str
    validation_sample_count: int
    preset_id: str
    preset_title: str
    desired_derived_model_alias: str
    adapter_name: str
    target_repo: str
    chunked_training: bool
    chunk_size: int


_DENSE_ATTENTION_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj"]
_DENSE_QKV_TARGETS = ["q_proj", "k_proj", "v_proj"]
_DENSE_MLP_TARGETS = ["gate_proj", "up_proj", "down_proj"]
_DENSE_FULL_TARGETS = [*_DENSE_ATTENTION_TARGETS, *_DENSE_MLP_TARGETS]

_MIXTRAL_ATTENTION_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj"]
_MIXTRAL_EXPERT_TARGETS = ["gate_proj", "up_proj", "down_proj"]
_MIXTRAL_FULL_TARGETS = [*_MIXTRAL_ATTENTION_TARGETS, *_MIXTRAL_EXPERT_TARGETS]

_FAMILY_PROFILES: dict[str, dict[str, object]] = {
    "llama": {
        "family_kind": "dense",
        "support_tier": "stable",
        "default_total_layers": 2,
        "default_target_preset": "attention_mlp",
        "default_target_modules": list(_DENSE_FULL_TARGETS),
        "target_module_presets": {
            "default": list(_DENSE_FULL_TARGETS),
            "attention": list(_DENSE_ATTENTION_TARGETS),
            "mlp": list(_DENSE_MLP_TARGETS),
            "attention_mlp": list(_DENSE_FULL_TARGETS),
            "full": list(_DENSE_FULL_TARGETS),
        },
        "module_templates": {
            "q_proj": "model.layers.{layer}.self_attn.q_proj",
            "k_proj": "model.layers.{layer}.self_attn.k_proj",
            "v_proj": "model.layers.{layer}.self_attn.v_proj",
            "o_proj": "model.layers.{layer}.self_attn.o_proj",
            "gate_proj": "model.layers.{layer}.mlp.gate_proj",
            "up_proj": "model.layers.{layer}.mlp.up_proj",
            "down_proj": "model.layers.{layer}.mlp.down_proj",
        },
    },
    "qwen": {
        "family_kind": "dense",
        "support_tier": "stable",
        "default_total_layers": 2,
        "default_target_preset": "attention_mlp",
        "default_target_modules": list(_DENSE_FULL_TARGETS),
        "target_module_presets": {
            "default": list(_DENSE_FULL_TARGETS),
            "attention": list(_DENSE_ATTENTION_TARGETS),
            "qkv": list(_DENSE_QKV_TARGETS),
            "mlp": list(_DENSE_MLP_TARGETS),
            "attention_mlp": list(_DENSE_FULL_TARGETS),
            "full": list(_DENSE_FULL_TARGETS),
        },
        "module_templates": {
            "q_proj": "model.layers.{layer}.self_attn.q_proj",
            "k_proj": "model.layers.{layer}.self_attn.k_proj",
            "v_proj": "model.layers.{layer}.self_attn.v_proj",
            "o_proj": "model.layers.{layer}.self_attn.o_proj",
            "gate_proj": "model.layers.{layer}.mlp.gate_proj",
            "up_proj": "model.layers.{layer}.mlp.up_proj",
            "down_proj": "model.layers.{layer}.mlp.down_proj",
        },
    },
    "gemma": {
        "family_kind": "dense",
        "support_tier": "stable",
        "default_total_layers": 2,
        "default_target_preset": "attention_mlp",
        "default_target_modules": list(_DENSE_FULL_TARGETS),
        "target_module_presets": {
            "default": list(_DENSE_FULL_TARGETS),
            "attention": list(_DENSE_ATTENTION_TARGETS),
            "gated_mlp": list(_DENSE_MLP_TARGETS),
            "mlp": list(_DENSE_MLP_TARGETS),
            "attention_mlp": list(_DENSE_FULL_TARGETS),
            "full": list(_DENSE_FULL_TARGETS),
        },
        "module_templates": {
            "q_proj": "model.layers.{layer}.self_attn.q_proj",
            "k_proj": "model.layers.{layer}.self_attn.k_proj",
            "v_proj": "model.layers.{layer}.self_attn.v_proj",
            "o_proj": "model.layers.{layer}.self_attn.o_proj",
            "gate_proj": "model.layers.{layer}.mlp.gate_proj",
            "up_proj": "model.layers.{layer}.mlp.up_proj",
            "down_proj": "model.layers.{layer}.mlp.down_proj",
        },
    },
    "kimi": {
        "family_kind": "dense",
        "support_tier": "stable",
        "default_total_layers": 2,
        "default_target_preset": "attention_mlp",
        "default_target_modules": list(_DENSE_FULL_TARGETS),
        "target_module_presets": {
            "default": list(_DENSE_FULL_TARGETS),
            "attention": list(_DENSE_ATTENTION_TARGETS),
            "qkv": list(_DENSE_QKV_TARGETS),
            "mlp": list(_DENSE_MLP_TARGETS),
            "attention_mlp": list(_DENSE_FULL_TARGETS),
            "full": list(_DENSE_FULL_TARGETS),
        },
        "module_templates": {
            "q_proj": "model.layers.{layer}.self_attn.q_proj",
            "k_proj": "model.layers.{layer}.self_attn.k_proj",
            "v_proj": "model.layers.{layer}.self_attn.v_proj",
            "o_proj": "model.layers.{layer}.self_attn.o_proj",
            "gate_proj": "model.layers.{layer}.mlp.gate_proj",
            "up_proj": "model.layers.{layer}.mlp.up_proj",
            "down_proj": "model.layers.{layer}.mlp.down_proj",
        },
    },
    "mixtral": {
        "family_kind": "moe",
        "support_tier": "experimental",
        "default_total_layers": 2,
        "default_target_preset": "attention",
        "default_target_modules": list(_MIXTRAL_ATTENTION_TARGETS),
        "target_module_presets": {
            "default": list(_MIXTRAL_ATTENTION_TARGETS),
            "attention": list(_MIXTRAL_ATTENTION_TARGETS),
            "experts": list(_MIXTRAL_EXPERT_TARGETS),
            "full": list(_MIXTRAL_FULL_TARGETS),
        },
        "module_templates": {
            "q_proj": "model.layers.{layer}.self_attn.q_proj",
            "k_proj": "model.layers.{layer}.self_attn.k_proj",
            "v_proj": "model.layers.{layer}.self_attn.v_proj",
            "o_proj": "model.layers.{layer}.self_attn.o_proj",
            "gate_proj": "model.layers.{layer}.block_sparse_moe.experts.*.w1",
            "up_proj": "model.layers.{layer}.block_sparse_moe.experts.*.w3",
            "down_proj": "model.layers.{layer}.block_sparse_moe.experts.*.w2",
        },
    },
}

_ADVANCED_FAMILY_HOOKS: dict[str, dict[str, str]] = {
    "mixtral": {
        "family_kind": "moe",
        "support_tier": "experimental",
        "training_ready": "true",
        "default_target_preset": "attention",
    },
    "qwen3moe": {
        "family_kind": "moe",
        "support_tier": "experimental",
        "training_ready": "false",
        "default_target_preset": "attention",
    },
    "deepseek-mla": {
        "family_kind": "moe",
        "support_tier": "experimental",
        "training_ready": "false",
        "default_target_preset": "attention",
    },
    "mistral4": {
        "family_kind": "dense",
        "support_tier": "experimental",
        "training_ready": "false",
        "default_target_preset": "attention",
    },
    "nemotron-h": {
        "family_kind": "advanced_text",
        "support_tier": "experimental",
        "training_ready": "false",
        "default_target_preset": "attention",
    },
}

_TRAINING_PRESETS: dict[str, dict[str, object]] = {
    "debug_fast": {
        "title": "Debug Fast",
        "rank": 8,
        "alpha": 16.0,
        "dropout": 0.0,
        "batch_size": 1,
        "epochs": 1,
        "learning_rate": 1e-4,
        "max_seq_length": 1024,
        "gradient_checkpointing": False,
    },
    "balanced_adapter": {
        "title": "Balanced Adapter",
        "rank": 16,
        "alpha": 32.0,
        "dropout": 0.05,
        "batch_size": 2,
        "epochs": 2,
        "learning_rate": 1e-4,
        "max_seq_length": 2048,
        "gradient_checkpointing": True,
    },
    "quality_adapter": {
        "title": "Quality Adapter",
        "rank": 32,
        "alpha": 64.0,
        "dropout": 0.05,
        "batch_size": 1,
        "epochs": 4,
        "learning_rate": 5e-5,
        "max_seq_length": 2048,
        "gradient_checkpointing": True,
    },
}


def normalize_training_config(
    *,
    source_model: common_pb2.ModelSpec,
    ext: dict[str, str],
    dataset_format: str,
    response_only_supported: bool,
    sample_count: int,
    validation_sample_count: int = 0,
) -> LoRATrainingConfig:
    if source_model.model_kind != "text":
        raise ModelOperationError(
            code="unsupported_model_family",
            message="LoRA training is only supported for text models in v1.",
            details={"model_kind": source_model.model_kind},
        )

    training_mode = ext.get("training_mode", "lora").strip().lower() or "lora"
    if training_mode not in {"lora", "qlora"}:
        raise ModelOperationError(
            code="unsupported_training_mode",
            message=f"Unsupported training_mode: {training_mode}",
        )
    if training_mode == "qlora" and _is_quantized_base_model(source_model) is False:
        raise ModelOperationError(
            code="unsupported_training_mode",
            message="training_mode=qlora requires a quantized base model.",
        )
    quantization_mode = "quantized_base" if training_mode == "qlora" else "none"
    preset_id = ext.get("preset_id", "").strip()
    preset = _resolve_training_preset(preset_id)

    family_id = _resolve_family_id(source_model)
    family_hooks = _resolve_family_hooks(source_model, family_id=family_id)
    profile = _FAMILY_PROFILES.get(family_id)
    if profile is None:
        raise ModelOperationError(
            code="unsupported_model_family",
            message=f"Unsupported LoRA family: {family_id}",
            details=family_hooks,
        )
    if family_hooks.get("training_ready", "true") != "true":
        raise ModelOperationError(
            code="unsupported_model_family",
            message=f"LoRA training hooks for family {family_id} are not productized yet.",
            details=family_hooks,
        )

    total_layer_count = _int_value(
        ext.get("total_layers", ""),
        default=_int_value(
            source_model.ext.get("text_layer_count", ""),
            default=int(profile["default_total_layers"]),
            minimum=1,
            field_name="text_layer_count",
        ),
        minimum=1,
        field_name="total_layers",
    )
    requested_num_layers = _int_value(
        ext.get("num_layers", ""),
        default=total_layer_count,
        minimum=1,
        field_name="num_layers",
    )
    num_layers = min(requested_num_layers, total_layer_count)
    selected_layer_indices = list(range(total_layer_count - num_layers, total_layer_count))

    configured_targets = _resolve_target_modules(ext.get("target_modules", ""), profile=profile)

    templates = profile["module_templates"]
    expanded_target_modules: list[str] = []
    for target_module in configured_targets:
        if target_module not in templates:
            raise ModelOperationError(
                code="unsupported_lora_target_module",
                message=f"Unsupported LoRA target module {target_module} for family {family_id}.",
                details={"family_id": family_id, "target_module": target_module},
            )
        template = str(templates[target_module])
        expanded_target_modules.extend(
            template.format(layer=layer_index)
            for layer_index in selected_layer_indices
        )

    backend_target_modules = _backend_target_modules(expanded_target_modules)

    response_only = _bool_value(
        ext.get("response_only", ""),
        default=dataset_format == "chat_messages",
    )
    if response_only and not response_only_supported:
        raise ModelOperationError(
            code="invalid_dataset_package",
            message="This dataset format cannot produce response-only supervision.",
            details={"format": dataset_format},
        )

    gradient_checkpointing = _bool_value(
        ext.get("gradient_checkpointing", ""),
        default=bool(preset.get("gradient_checkpointing", False)),
    )
    gradient_accumulation = _int_value(
        ext.get("gradient_accumulation", ""),
        default=int(preset.get("gradient_accumulation", 1)),
        minimum=1,
        field_name="gradient_accumulation",
    )
    mask_prompt = _bool_value(ext.get("mask_prompt", ""), default=response_only)
    batch_size = min(
        max(
            1,
            _int_value(
                ext.get("batch_size", ""),
                default=int(preset.get("batch_size", min(4, max(sample_count, 1)))),
                minimum=1,
                field_name="batch_size",
            ),
        ),
        max(sample_count, 1),
    )
    epochs = _int_value(
        ext.get("epochs", ""),
        default=int(preset.get("epochs", 1)),
        minimum=1,
        field_name="epochs",
    )
    iters = max(1, math.ceil(sample_count * epochs / batch_size))
    max_steps_raw = ext.get("max_steps", "").strip()
    max_steps = (
        _int_value(
            max_steps_raw,
            default=0,
            minimum=1,
            field_name="max_steps",
        )
        if max_steps_raw
        else 0
    )
    if max_steps > 0:
        iters = min(iters, max_steps)
    max_seq_length = _int_value(
        ext.get("max_seq_length", ""),
        default=min(int(source_model.max_context or 2048), int(preset.get("max_seq_length", 2048))),
        minimum=1,
        field_name="max_seq_length",
    )
    chunked_training = _bool_value(ext.get("chunked_training", ""), default=False)
    chunk_size_raw = ext.get("chunk_size", "").strip()
    if chunk_size_raw:
        chunk_size = _int_value(
            chunk_size_raw,
            default=max_seq_length,
            minimum=512,
            field_name="chunk_size",
        )
        if chunk_size > max_seq_length:
            raise ModelOperationError(
                code="invalid_chunk_size",
                message=(
                    f"chunk_size {chunk_size} must be <= max_seq_length "
                    f"{max_seq_length}."
                ),
            )
    else:
        chunk_size = max_seq_length
    steps_per_report = min(max(1, iters), 10)
    steps_per_eval = max(iters, 1) if validation_sample_count > 0 else 0
    steps_per_save = max(iters, 1)
    validation_split = ext.get("hf_valid_split", "").strip()
    validation_strategy = "hf_split" if validation_split and validation_sample_count > 0 else "none"

    return LoRATrainingConfig(
        training_mode=training_mode,
        quantization_mode=quantization_mode,
        family_id=family_id,
        rank=_int_value(ext.get("rank", ""), default=int(preset.get("rank", 8)), minimum=1, field_name="rank"),
        alpha=_float_value(ext.get("alpha", ""), default=float(preset.get("alpha", 20.0)), minimum=0.0, field_name="alpha"),
        dropout=_float_value(ext.get("dropout", ""), default=float(preset.get("dropout", 0.0)), minimum=0.0, field_name="dropout"),
        target_modules=configured_targets,
        expanded_target_modules=expanded_target_modules,
        backend_target_modules=backend_target_modules,
        selected_layer_indices=selected_layer_indices,
        total_layer_count=total_layer_count,
        num_layers=num_layers,
        learning_rate=_float_value(
            ext.get("learning_rate", ""),
            default=float(preset.get("learning_rate", 1e-5)),
            minimum=0.0,
            field_name="learning_rate",
        ),
        batch_size=batch_size,
        epochs=epochs,
        iters=iters,
        max_steps=max_steps,
        response_only=response_only,
        gradient_checkpointing=gradient_checkpointing,
        gradient_accumulation=gradient_accumulation,
        mask_prompt=mask_prompt,
        max_seq_length=max_seq_length,
        steps_per_report=steps_per_report,
        steps_per_eval=steps_per_eval,
        steps_per_save=steps_per_save,
        validation_strategy=validation_strategy,
        validation_split=validation_split,
        validation_sample_count=validation_sample_count,
        preset_id=preset_id,
        preset_title=str(preset.get("title", "")),
        desired_derived_model_alias=ext.get("derived_model_alias", "").strip(),
        adapter_name=ext.get("adapter_name", "melix-adapter").strip() or "melix-adapter",
        target_repo=ext.get("target_repo", "").strip(),
        chunked_training=chunked_training,
        chunk_size=chunk_size,
    )


def _resolve_training_preset(preset_id: str) -> dict[str, object]:
    if not preset_id:
        return {}
    preset = _TRAINING_PRESETS.get(preset_id)
    if preset is None:
        raise ModelOperationError(
            code="invalid_training_preset",
            message=f"Unknown training preset: {preset_id}",
        )
    return preset


def _resolve_family_id(source_model: common_pb2.ModelSpec) -> str:
    explicit_lora = source_model.ext.get("melix.lora.family_id", "").strip().lower()
    if explicit_lora:
        return explicit_lora

    explicit = source_model.ext.get("text_family_id", "").strip().lower()
    if explicit:
        return explicit

    detected = source_model.ext.get("detected_family_id", "").strip().lower()
    if detected:
        return detected

    searchable = " ".join(
        [
            source_model.model_path.lower(),
            source_model.model_id.lower(),
            source_model.revision.lower(),
        ]
    )
    if "mixtral" in searchable:
        return "mixtral"
    if "qwen3" in searchable and "moe" in searchable:
        return "qwen3moe"
    if "qwen" in searchable:
        return "qwen"
    if "gemma" in searchable:
        return "gemma"
    if "deepseek" in searchable:
        return "deepseek-mla"
    if "mistral4" in searchable or "mistral-small-4" in searchable:
        return "mistral4"
    if "nemotron_h" in searchable or "nemotron-h" in searchable:
        return "nemotron-h"
    if "kimi" in searchable or "moonshot" in searchable:
        return "kimi"
    if any(token in searchable for token in ("mistral", "llama", "text")):
        return "llama"
    return "llama"


def _resolve_family_hooks(source_model: common_pb2.ModelSpec, *, family_id: str) -> dict[str, str]:
    family_hooks = dict(_ADVANCED_FAMILY_HOOKS.get(family_id, {}))
    ext = source_model.ext
    family_hooks["family_id"] = family_id
    family_hooks["family_kind"] = (
        ext.get("melix.lora.family_kind", "").strip().lower()
        or family_hooks.get("family_kind", "dense")
    )
    family_hooks["support_tier"] = (
        ext.get("melix.lora.support_tier", "").strip().lower()
        or family_hooks.get("support_tier", str(_FAMILY_PROFILES.get(family_id, {}).get("support_tier", "stable")))
    )
    family_hooks["training_ready"] = (
        ext.get("melix.lora.training_ready", "").strip().lower()
        or family_hooks.get("training_ready", "true")
    )
    family_hooks["default_target_preset"] = (
        ext.get("melix.lora.default_target_preset", "").strip().lower()
        or family_hooks.get(
            "default_target_preset",
            str(_FAMILY_PROFILES.get(family_id, {}).get("default_target_preset", "default")),
        )
    )
    return family_hooks


def _resolve_target_modules(raw_value: str, *, profile: dict[str, object]) -> list[str]:
    presets = {
        str(key).strip().lower(): [str(item).strip().lower() for item in value]
        for key, value in profile.get("target_module_presets", {}).items()
    }
    default_targets = [str(item).strip().lower() for item in profile["default_target_modules"]]
    requested = [item.strip().lower() for item in raw_value.split(",") if item.strip()]
    if not requested:
        return default_targets

    resolved_targets: list[str] = []
    seen: set[str] = set()
    for requested_target in requested:
        target_key = requested_target.lstrip("@")
        expanded_targets = presets.get(target_key, [requested_target])
        for expanded_target in expanded_targets:
            if expanded_target not in seen:
                seen.add(expanded_target)
                resolved_targets.append(expanded_target)
    return resolved_targets


def _backend_target_modules(expanded_target_modules: Iterable[str]) -> list[str]:
    backend_modules: list[str] = []
    seen: set[str] = set()
    for module_path in expanded_target_modules:
        _, _, suffix = module_path.partition(".self_attn.")
        if suffix:
            backend_module = f"self_attn.{suffix}"
        else:
            prefix = "model.layers."
            if module_path.startswith(prefix):
                remaining = module_path[len(prefix):]
                _, _, backend_module = remaining.partition(".")
            else:
                backend_module = module_path
        if backend_module not in seen:
            seen.add(backend_module)
            backend_modules.append(backend_module)
    return backend_modules


def _is_quantized_base_model(source_model: common_pb2.ModelSpec) -> bool:
    if source_model.quant_profile_id.strip():
        return True

    searchable = " ".join(
        [
            source_model.model_id.lower(),
            source_model.model_path.lower(),
            source_model.revision.lower(),
        ]
    )
    return any(
        token in searchable
        for token in ("4bit", "8bit", "q4", "q8", "optiq")
    )


def _int_value(raw_value: str, *, default: int, minimum: int, field_name: str) -> int:
    value = default if not raw_value else int(raw_value)
    if value < minimum:
        raise ModelOperationError(
            code="invalid_argument",
            message=f"{field_name} must be at least {minimum}.",
        )
    return value


def _float_value(raw_value: str, *, default: float, minimum: float, field_name: str) -> float:
    value = default if not raw_value else float(raw_value)
    if value < minimum:
        raise ModelOperationError(
            code="invalid_argument",
            message=f"{field_name} must be at least {minimum}.",
        )
    return value


def _bool_value(raw_value: str, *, default: bool) -> bool:
    if not raw_value:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}
