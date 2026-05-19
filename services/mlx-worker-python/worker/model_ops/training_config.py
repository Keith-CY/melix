from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Iterable

from packages.protocol.python.worker.v1 import common_pb2

from worker.model_ops.adapter_capabilities import (
    DEFAULT_ADAPTER_CAPABILITY_REGISTRY,
    UNSUPPORTED_REASON_MISSING_ADAPTER_PROVIDER,
    UNSUPPORTED_REASON_MISSING_QUANTIZATION_PROVIDER,
    UNSUPPORTED_REASON_UNSUPPORTED_BACKEND,
    UNSUPPORTED_REASON_UNSUPPORTED_QUANTIZED_BASE,
    AdapterCapabilityRegistry,
)
from worker.model_ops.errors import ModelOperationError
from worker.model_ops.quantization_metadata import EXPLICIT_QUANTIZED_PROFILE_IDS


@dataclass(frozen=True)
class AlignmentTrainingConfig:
    alignment_algorithm: str
    dataset_contract: str
    reference_model_path: str = ""
    reward_model_manifest_path: str = ""
    grpo_candidate_count: int = 0
    kl_penalty: float = 0.0
    preference_margin_target: float = 0.0
    candidate_generation_mode: str = "scored_trace"
    candidate_scoring_mode: str = "dataset_score"
    candidate_generation_temperature: float = 0.0
    candidate_generation_top_p: float = 1.0
    candidate_generation_top_k: int = 0
    candidate_generation_max_tokens: int = 128


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
    training_objective: str = "supervised_finetuning"
    adapter_algorithm: str = "lora"
    adapter_family: str = "lora"
    adapter_capabilities: dict[str, bool] = field(default_factory=dict)
    backend_supported: bool = True
    unsupported_reason: str = ""
    adapter_loader_kwargs: dict[str, str] = field(default_factory=dict)
    base_quantization_method: str = ""
    preference_loss: str = ""
    dataset_contract: str = "sft"
    alignment: AlignmentTrainingConfig | None = None


_DENSE_ATTENTION_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj"]
_DENSE_QKV_TARGETS = ["q_proj", "k_proj", "v_proj"]
_DENSE_MLP_TARGETS = ["gate_proj", "up_proj", "down_proj"]
_DENSE_FULL_TARGETS = [*_DENSE_ATTENTION_TARGETS, *_DENSE_MLP_TARGETS]

_MIXTRAL_ATTENTION_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj"]
_MIXTRAL_EXPERT_TARGETS = ["gate_proj", "up_proj", "down_proj"]
_MIXTRAL_FULL_TARGETS = [*_MIXTRAL_ATTENTION_TARGETS, *_MIXTRAL_EXPERT_TARGETS]

_QWEN3MOE_ATTENTION_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj"]
_QWEN3MOE_QKV_TARGETS = ["q_proj", "k_proj", "v_proj"]
_QWEN3MOE_EXPERT_TARGETS = ["gate_proj", "up_proj", "down_proj"]
_QWEN3MOE_FULL_TARGETS = [*_QWEN3MOE_ATTENTION_TARGETS, *_QWEN3MOE_EXPERT_TARGETS]

_UNSAFE_QUANTIZED_LORA_TARGETS = {
    "embed_tokens",
    "lm_head",
    "output_head",
    "output_projection",
}
_CONFIRMED_EXPERT_COUNT_SOURCES = {"config"}
_QUANTIZED_MODEL_PATTERN = re.compile(r"(?<![a-z0-9])(?:4bit|8bit|q4|q8|optiq)(?![a-z0-9])")
_SFT_TRAINING_MODES = {"lora", "qlora", "dora"}
_PREFERENCE_TRAINING_MODES = {"dpo", "orpo", "cpo"}
_RL_TRAINING_MODES = {"grpo", "rlhf"}
_CPT_TRAINING_MODES = {"cpt"}
_TRAINING_OBJECTIVE_EXT_KEYS = (
    "training_objective",
    "melix.training_objective",
)
_SUPPORTED_TRAINING_MODES = (
    _SFT_TRAINING_MODES
    | _PREFERENCE_TRAINING_MODES
    | _RL_TRAINING_MODES
    | _CPT_TRAINING_MODES
)
_SUPPORTED_COMPONENT_SCOPES: frozenset[str] = frozenset({"text_backbone"})
_BUILTIN_QUANTIZATION_METHODS: frozenset[str] = frozenset(
    {"mlx", "mlx_lm", "mlx-lm", "quant_profile", "path_hint"}
)

_NORMALIZED_TARGET_MODULE_PRESETS_KEY = "_normalized_target_module_presets"
_NORMALIZED_DEFAULT_TARGET_MODULES_KEY = "_normalized_default_target_modules"
_NORMALIZED_TARGET_MODULES_CACHE_KEY = "_normalized_target_modules_cache"

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
    "qwen3moe": {
        "family_kind": "moe",
        "support_tier": "experimental",
        "default_total_layers": 2,
        "default_expert_count": 128,
        "default_target_preset": "attention",
        "default_target_modules": list(_QWEN3MOE_ATTENTION_TARGETS),
        "target_module_presets": {
            "default": list(_QWEN3MOE_ATTENTION_TARGETS),
            "attention": list(_QWEN3MOE_ATTENTION_TARGETS),
            "qkv": list(_QWEN3MOE_QKV_TARGETS),
            "experts": list(_QWEN3MOE_EXPERT_TARGETS),
            # `full` is an operator-facing alias for the explicit attention+experts preset.
            "attention_experts": list(_QWEN3MOE_FULL_TARGETS),
            "full": list(_QWEN3MOE_FULL_TARGETS),
        },
        "module_templates": {
            "q_proj": "model.layers.{layer}.self_attn.q_proj",
            "k_proj": "model.layers.{layer}.self_attn.k_proj",
            "v_proj": "model.layers.{layer}.self_attn.v_proj",
            "o_proj": "model.layers.{layer}.self_attn.o_proj",
            "gate_proj": "model.layers.{layer}.mlp.experts.{expert}.gate_proj",
            "up_proj": "model.layers.{layer}.mlp.experts.{expert}.up_proj",
            "down_proj": "model.layers.{layer}.mlp.experts.{expert}.down_proj",
        },
    },
}


def _normalize_target_module_presets(profile: dict[str, object]) -> dict[str, tuple[str, ...]]:
    return {
        str(key).strip().lower(): tuple(str(item).strip().lower() for item in value)
        for key, value in profile.get("target_module_presets", {}).items()
    }


def _normalize_default_target_modules(profile: dict[str, object]) -> tuple[str, ...]:
    return tuple(str(item).strip().lower() for item in profile["default_target_modules"])


for _profile in _FAMILY_PROFILES.values():
    _profile[_NORMALIZED_TARGET_MODULE_PRESETS_KEY] = _normalize_target_module_presets(_profile)
    _profile[_NORMALIZED_DEFAULT_TARGET_MODULES_KEY] = _normalize_default_target_modules(_profile)
    _profile[_NORMALIZED_TARGET_MODULES_CACHE_KEY] = {}

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
    adapter_registry: AdapterCapabilityRegistry | None = None,
) -> LoRATrainingConfig:
    _validate_lora_training_surface(source_model)

    training_mode = ext.get("training_mode", "lora").strip().lower() or "lora"
    if training_mode not in _SUPPORTED_TRAINING_MODES:
        raise ModelOperationError(
            code="unsupported_training_mode",
            message=f"Unsupported training_mode: {training_mode}",
        )
    mode_contract = _resolve_training_mode_contract(training_mode, dataset_format)
    _validate_requested_training_objective(
        ext,
        contract=mode_contract,
        training_mode=training_mode,
        dataset_format=dataset_format,
    )
    alignment = _resolve_alignment_config(
        training_mode=training_mode,
        dataset_contract=mode_contract["dataset_contract"],
        ext=ext,
    )
    adapter_family = _resolve_adapter_family(ext, training_mode=training_mode, mode_contract=mode_contract)
    registry = adapter_registry or DEFAULT_ADAPTER_CAPABILITY_REGISTRY
    adapter_record = registry.resolve(adapter_family)
    if adapter_record is None:
        raise ModelOperationError(
            code=UNSUPPORTED_REASON_MISSING_ADAPTER_PROVIDER,
            message=f"No adapter provider is registered for adapter_family={adapter_family}.",
            details={"adapter_family": adapter_family, "training_mode": training_mode},
        )
    if adapter_record.backend_supported is False:
        raise ModelOperationError(
            code=adapter_record.unsupported_reason or UNSUPPORTED_REASON_UNSUPPORTED_BACKEND,
            message=f"Adapter family {adapter_record.adapter_family} is not supported by backend {adapter_record.backend}.",
            details={
                "adapter_family": adapter_record.adapter_family,
                "backend": adapter_record.backend,
                "unsupported_reason": adapter_record.unsupported_reason,
            },
        )

    base_quantization_method = _base_quantization_method(source_model)
    quantized_base_model = bool(base_quantization_method)
    if quantized_base_model:
        _validate_quantization_provider(source_model, base_quantization_method=base_quantization_method)
    if quantized_base_model and adapter_record.capabilities.quantized_base_supported is False:
        raise ModelOperationError(
            code=UNSUPPORTED_REASON_UNSUPPORTED_QUANTIZED_BASE,
            message=f"Adapter family {adapter_record.adapter_family} does not support quantized base models.",
            details={
                "adapter_family": adapter_record.adapter_family,
                "training_mode": training_mode,
                "base_quantization_method": base_quantization_method,
            },
        )
    if training_mode == "qlora" and quantized_base_model is False:
        raise ModelOperationError(
            code=UNSUPPORTED_REASON_UNSUPPORTED_QUANTIZED_BASE,
            message="training_mode=qlora requires a quantized base model.",
            details={"adapter_family": adapter_record.adapter_family, "training_mode": training_mode},
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
    if training_mode == "qlora" or quantized_base_model:
        _reject_unsafe_quantized_lora_targets(
            configured_targets,
            family_id=family_id,
            training_mode=training_mode,
            quantization_mode=quantization_mode,
        )

    templates = profile["module_templates"]
    expert_count: int | None = None
    expanded_target_modules: list[str] = []
    for target_module in configured_targets:
        if target_module not in templates:
            raise ModelOperationError(
                code="unsupported_lora_target_module",
                message=f"Unsupported LoRA target module {target_module} for family {family_id}.",
                details={"family_id": family_id, "target_module": target_module},
            )
        template = str(templates[target_module])
        if "{expert}" in template:
            if expert_count is None:
                expert_count = _resolve_expert_count(source_model, profile=profile)
            expanded_target_modules.extend(
                template.format(layer=layer_index, expert=expert_index)
                for layer_index in selected_layer_indices
                for expert_index in range(expert_count)
            )
        else:
            expanded_target_modules.extend(
                template.format(layer=layer_index)
                for layer_index in selected_layer_indices
            )

    backend_target_modules = _backend_target_modules(expanded_target_modules)

    response_only = _bool_value(
        ext.get("response_only", ""),
        default=dataset_format in {"chat_messages", "agentic_tool_trace"},
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
        # chunk_size is always validated (even when chunked_training is off)
        # so a mis-configured value fails fast at config time rather than
        # silently going unused. Both the lower-bound and upper-bound checks
        # raise ``invalid_chunk_size`` for a consistent error code.
        try:
            parsed_chunk_size = int(chunk_size_raw)
        except ValueError as exc:
            raise ModelOperationError(
                code="invalid_chunk_size",
                message=f"chunk_size must be an integer, got {chunk_size_raw!r}.",
            ) from exc
        if parsed_chunk_size < 512:
            raise ModelOperationError(
                code="invalid_chunk_size",
                message=(
                    f"chunk_size {parsed_chunk_size} must be >= 512."
                ),
            )
        if parsed_chunk_size > max_seq_length:
            raise ModelOperationError(
                code="invalid_chunk_size",
                message=(
                    f"chunk_size {parsed_chunk_size} must be <= max_seq_length "
                    f"{max_seq_length}."
                ),
            )
        chunk_size = parsed_chunk_size
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
        training_objective=mode_contract["training_objective"],
        adapter_algorithm=adapter_record.adapter_algorithm,
        adapter_family=adapter_record.adapter_family,
        adapter_capabilities=adapter_record.capabilities.as_manifest(),
        backend_supported=adapter_record.backend_supported,
        unsupported_reason=adapter_record.unsupported_reason,
        adapter_loader_kwargs=dict(adapter_record.loader_kwargs),
        base_quantization_method=base_quantization_method,
        preference_loss=mode_contract["preference_loss"],
        dataset_contract=mode_contract["dataset_contract"],
        alignment=alignment,
    )


def _resolve_training_mode_contract(training_mode: str, dataset_format: str) -> dict[str, str]:
    if training_mode in _SFT_TRAINING_MODES:
        if dataset_format not in {
            "chat_messages",
            "prompt_completion",
            "text_completion",
            "agentic_tool_trace",
        }:
            raise ModelOperationError(
                code="invalid_dataset_package",
                message="SFT training modes require supervised training datasets.",
                details={
                    "training_mode": training_mode,
                    "required_format": (
                        "chat_messages,prompt_completion,text_completion,"
                        "agentic_tool_trace"
                    ),
                    "actual_format": dataset_format,
                },
            )
        training_objective = (
            "agentic_sft"
            if dataset_format == "agentic_tool_trace"
            else "supervised_finetuning"
        )
        return {
            "training_objective": training_objective,
            "adapter_algorithm": "dora" if training_mode == "dora" else "lora",
            "preference_loss": "",
            "dataset_contract": (
                "agentic_tool_trace"
                if dataset_format == "agentic_tool_trace"
                else "sft"
            ),
        }

    if training_mode in _PREFERENCE_TRAINING_MODES:
        if dataset_format != "preference_pair":
            raise ModelOperationError(
                code="invalid_dataset_package",
                message="Preference training modes require preference_pair datasets.",
                details={
                    "training_mode": training_mode,
                    "required_format": "preference_pair",
                    "actual_format": dataset_format,
                },
            )
        return {
            "training_objective": "preference",
            "adapter_algorithm": "lora",
            "preference_loss": training_mode,
            "dataset_contract": "preference_pair",
        }

    if training_mode == "grpo":
        if dataset_format != "prompt_candidate":
            raise ModelOperationError(
                code="invalid_dataset_package",
                message="GRPO alignment requires prompt_candidate datasets.",
                details={
                    "training_mode": training_mode,
                    "required_format": "prompt_candidate",
                    "actual_format": dataset_format,
                },
            )
        return {
            "training_objective": "alignment_rl",
            "adapter_algorithm": "lora",
            "preference_loss": "",
            "dataset_contract": "prompt_candidate",
        }

    if training_mode == "rlhf":
        if dataset_format != "reward_scored":
            raise ModelOperationError(
                code="invalid_dataset_package",
                message="RLHF alignment requires reward_scored datasets.",
                details={
                    "training_mode": training_mode,
                    "required_format": "reward_scored",
                    "actual_format": dataset_format,
                },
            )
        return {
            "training_objective": "alignment_rl",
            "adapter_algorithm": "lora",
            "preference_loss": "",
            "dataset_contract": "reward_scored",
        }

    if training_mode in _CPT_TRAINING_MODES and dataset_format != "text_completion":
        raise ModelOperationError(
            code="invalid_dataset_package",
            message="Continual pretraining requires text_completion datasets.",
            details={
                "training_mode": training_mode,
                "required_format": "text_completion",
                "actual_format": dataset_format,
            },
        )
    return {
        "training_objective": "continual_pretraining",
        "adapter_algorithm": "lora",
        "preference_loss": "",
        "dataset_contract": "text_completion",
    }


def _requested_training_objective(ext: dict[str, str]) -> str:
    for key in _TRAINING_OBJECTIVE_EXT_KEYS:
        value = ext.get(key, "").strip().lower()
        if value:
            return value
    return ""


def _validate_requested_training_objective(
    ext: dict[str, str],
    *,
    contract: dict[str, str],
    training_mode: str,
    dataset_format: str,
) -> None:
    requested_objective = _requested_training_objective(ext)
    if not requested_objective:
        return
    required_objective = contract["training_objective"]
    if requested_objective == required_objective:
        return
    raise ModelOperationError(
        code="invalid_training_objective",
        message=(
            f"training_objective={requested_objective} is not compatible "
            f"with training_mode={training_mode}."
        ),
        details={
            "training_mode": training_mode,
            "training_objective": requested_objective,
            "required_training_objective": required_objective,
            "dataset_format": dataset_format,
        },
    )


def _resolve_adapter_family(
    ext: dict[str, str],
    *,
    training_mode: str,
    mode_contract: dict[str, str],
) -> str:
    explicit_family = (
        ext.get("adapter_family", "").strip()
        or ext.get("melix.adapter.family", "").strip()
        or ext.get("melix.adapter_family", "").strip()
    )
    if explicit_family:
        return explicit_family
    if training_mode in {"qlora", "dora"}:
        return training_mode
    return mode_contract["adapter_algorithm"]


def _resolve_alignment_config(
    *,
    training_mode: str,
    dataset_contract: str,
    ext: dict[str, str],
) -> AlignmentTrainingConfig | None:
    if training_mode not in (_PREFERENCE_TRAINING_MODES | _RL_TRAINING_MODES):
        return None

    grpo_candidate_count = 0
    if training_mode == "grpo":
        raw_candidate_count = ext.get("grpo_candidate_count", "").strip()
        if not raw_candidate_count:
            raise ModelOperationError(
                code="invalid_alignment_config",
                message="training_mode=grpo requires grpo_candidate_count.",
                details={
                    "training_mode": training_mode,
                    "missing_field": "grpo_candidate_count",
                },
            )
        grpo_candidate_count = _int_value(
            raw_candidate_count,
            default=0,
            minimum=2,
            field_name="grpo_candidate_count",
        )

    reward_model_manifest_path = ext.get("reward_model_manifest_path", "").strip()
    if training_mode == "rlhf" and not reward_model_manifest_path:
        raise ModelOperationError(
            code="invalid_alignment_config",
            message="training_mode=rlhf requires reward_model_manifest_path.",
            details={
                "training_mode": training_mode,
                "missing_field": "reward_model_manifest_path",
            },
        )

    candidate_generation_mode = (
        ext.get("candidate_generation_mode", "").strip().lower()
        or ext.get("grpo_candidate_generation_mode", "").strip().lower()
        or "scored_trace"
    )
    if candidate_generation_mode not in {"scored_trace", "runtime_generate"}:
        raise ModelOperationError(
            code="invalid_alignment_config",
            message=f"Unsupported candidate_generation_mode: {candidate_generation_mode}",
            details={
                "training_mode": training_mode,
                "candidate_generation_mode": candidate_generation_mode,
            },
        )
    if training_mode != "grpo" and candidate_generation_mode != "scored_trace":
        raise ModelOperationError(
            code="invalid_alignment_config",
            message="candidate_generation_mode=runtime_generate is only supported for GRPO.",
            details={
                "training_mode": training_mode,
                "candidate_generation_mode": candidate_generation_mode,
                "supported_training_mode": "grpo",
            },
        )

    candidate_scoring_mode = (
        ext.get("candidate_scoring_mode", "").strip().lower()
        or ext.get("grpo_candidate_scoring_mode", "").strip().lower()
        or ("seed_overlap_proxy" if candidate_generation_mode == "runtime_generate" else "dataset_score")
    )
    if training_mode in _RL_TRAINING_MODES:
        expected_scoring_modes = (
            {"seed_overlap_proxy", "reward_model"}
            if candidate_generation_mode == "runtime_generate"
            else {"dataset_score", "reward_model"}
        )
    else:
        expected_scoring_modes = {"dataset_score"}
    if candidate_scoring_mode not in expected_scoring_modes:
        raise ModelOperationError(
            code="invalid_alignment_config",
            message=(
                f"candidate_scoring_mode={candidate_scoring_mode} is not supported "
                f"for candidate_generation_mode={candidate_generation_mode}."
            ),
            details={
                "training_mode": training_mode,
                "candidate_generation_mode": candidate_generation_mode,
                "candidate_scoring_mode": candidate_scoring_mode,
                "supported_candidate_scoring_modes": ",".join(sorted(expected_scoring_modes)),
            },
        )
    if candidate_scoring_mode == "reward_model" and not reward_model_manifest_path:
        raise ModelOperationError(
            code="invalid_alignment_config",
            message="candidate_scoring_mode=reward_model requires reward_model_manifest_path.",
            details={
                "training_mode": training_mode,
                "candidate_scoring_mode": candidate_scoring_mode,
                "missing_field": "reward_model_manifest_path",
            },
        )

    return AlignmentTrainingConfig(
        alignment_algorithm=training_mode,
        dataset_contract=dataset_contract,
        reference_model_path=ext.get("reference_model_path", "").strip(),
        reward_model_manifest_path=reward_model_manifest_path,
        grpo_candidate_count=grpo_candidate_count,
        kl_penalty=_float_value(
            ext.get("kl_penalty", ""),
            default=0.0,
            minimum=0.0,
            field_name="kl_penalty",
        ),
        preference_margin_target=_float_value(
            ext.get("preference_margin_target", ""),
            default=0.0,
            minimum=0.0,
            field_name="preference_margin_target",
        ),
        candidate_generation_mode=candidate_generation_mode,
        candidate_scoring_mode=candidate_scoring_mode,
        candidate_generation_temperature=_float_value(
            ext.get("candidate_generation_temperature", "")
            or ext.get("grpo_candidate_generation_temperature", ""),
            default=0.0,
            minimum=0.0,
            field_name="candidate_generation_temperature",
        ),
        candidate_generation_top_p=_float_value(
            ext.get("candidate_generation_top_p", "")
            or ext.get("grpo_candidate_generation_top_p", ""),
            default=1.0,
            minimum=0.0,
            field_name="candidate_generation_top_p",
        ),
        candidate_generation_top_k=_int_value(
            ext.get("candidate_generation_top_k", "")
            or ext.get("grpo_candidate_generation_top_k", ""),
            default=0,
            minimum=0,
            field_name="candidate_generation_top_k",
        ),
        candidate_generation_max_tokens=_int_value(
            ext.get("candidate_generation_max_tokens", "")
            or ext.get("grpo_candidate_generation_max_tokens", ""),
            default=128,
            minimum=1,
            field_name="candidate_generation_max_tokens",
        ),
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


def _validate_lora_training_surface(source_model: common_pb2.ModelSpec) -> None:
    if source_model.model_kind == "text":
        return

    ext = source_model.ext
    adapter_scope = ext.get("melix.lora.adapter_scope", "").strip().lower()
    training_surface = ext.get("melix.lora.training_surface", "").strip().lower() or adapter_scope
    training_ready = ext.get("melix.lora.training_ready", "").strip().lower()
    component_lora_supported = ext.get(f"melix.component.{adapter_scope}.lora_supported", "").strip().lower()
    component_training_ready = ext.get(f"melix.component.{adapter_scope}.training_ready", "").strip().lower()
    component_model_type = (
        ext.get("melix.lora.component_model_type", "").strip().lower()
        or ext.get(f"melix.component.{adapter_scope}.model_type", "").strip().lower()
    )
    component_family = (
        ext.get("melix.lora.family_id", "").strip().lower()
        or ext.get(f"melix.component.{adapter_scope}.family_id", "").strip().lower()
    )

    if (
        adapter_scope in _SUPPORTED_COMPONENT_SCOPES
        and training_surface in _SUPPORTED_COMPONENT_SCOPES
        and training_ready == "true"
        and component_lora_supported == "true"
        and component_training_ready == "true"
        and component_model_type
        and component_family
    ):
        return

    raise ModelOperationError(
        code="unsupported_model_family",
        message="LoRA training is only supported for text models or training-ready text_backbone components.",
        details={
            "model_kind": source_model.model_kind,
            "adapter_scope": adapter_scope,
            "training_surface": training_surface,
            "training_ready": training_ready,
            "component_lora_supported": component_lora_supported,
            "component_training_ready": component_training_ready,
            "component_model_type": component_model_type,
            "component_family": component_family,
        },
    )


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
    cache = profile.get(_NORMALIZED_TARGET_MODULES_CACHE_KEY)
    if not isinstance(cache, dict):
        cache = {}
        profile[_NORMALIZED_TARGET_MODULES_CACHE_KEY] = cache
    cached_targets = cache.get(raw_value)
    if isinstance(cached_targets, tuple):
        # Cache stores immutable tuples; list() produces a fresh copy per call so
        # callers can safely iterate without risk of mutating shared cache state.
        return list(cached_targets)

    presets = profile.get(_NORMALIZED_TARGET_MODULE_PRESETS_KEY)
    if not isinstance(presets, dict):
        presets = _normalize_target_module_presets(profile)
    default_targets = profile.get(_NORMALIZED_DEFAULT_TARGET_MODULES_KEY)
    if not isinstance(default_targets, tuple):
        default_targets = _normalize_default_target_modules(profile)
    resolved_targets: list[str] = []
    seen: set[str] = set()
    requested_found = False
    for raw_target in raw_value.split(","):
        requested_target = raw_target.strip().lower()
        if not requested_target:
            continue
        requested_found = True
        target_key = requested_target.lstrip("@")
        expanded_targets = presets.get(target_key, (requested_target,))
        for expanded_target in expanded_targets:
            if expanded_target not in seen:
                seen.add(expanded_target)
                resolved_targets.append(expanded_target)
    resolved_tuple = tuple(resolved_targets) if requested_found else default_targets
    cache[raw_value] = resolved_tuple
    return list(resolved_tuple)


def _reject_unsafe_quantized_lora_targets(
    target_modules: Iterable[str],
    *,
    family_id: str,
    training_mode: str,
    quantization_mode: str,
) -> None:
    for target_module in target_modules:
        normalized = target_module.strip().lower()
        leaf = normalized.replace("/", ".").rsplit(".", maxsplit=1)[-1]
        if normalized in _UNSAFE_QUANTIZED_LORA_TARGETS or leaf in _UNSAFE_QUANTIZED_LORA_TARGETS:
            raise ModelOperationError(
                code="unsupported_lora_target_module",
                message=(
                    "Quantized LoRA training does not support embedding, "
                    f"LM head, or output projection target module {target_module}."
                ),
                details={
                    "family_id": family_id,
                    "target_module": target_module,
                    "training_mode": training_mode,
                    "quantization_mode": quantization_mode,
                    "unsupported_target_class": "embedding_or_head",
                },
            )


def _resolve_expert_count(
    source_model: common_pb2.ModelSpec,
    *,
    profile: dict[str, object],
) -> int:
    raw_expert_count = source_model.ext.get("melix.text.moe.expert_count", "").strip()
    expert_count_source = source_model.ext.get("melix.text.moe.expert_count_source", "").strip().lower()
    if not raw_expert_count or expert_count_source not in _CONFIRMED_EXPERT_COUNT_SOURCES:
        raise ModelOperationError(
            code="unsupported_lora_target_module",
            message="Expert LoRA target presets require config-confirmed MoE expert count metadata.",
            details={
                "family_id": _resolve_family_id(source_model),
                "target_module_class": "expert",
                "metadata_key": "melix.text.moe.expert_count",
                "metadata_source_key": "melix.text.moe.expert_count_source",
                "metadata_source": expert_count_source or "missing",
                "confirmed_sources": ",".join(sorted(_CONFIRMED_EXPERT_COUNT_SOURCES)),
            },
        )
    return _int_value(
        raw_expert_count,
        default=0,
        minimum=1,
        field_name="melix.text.moe.expert_count",
    )


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
    return bool(_base_quantization_method(source_model))


def _base_quantization_method(source_model: common_pb2.ModelSpec) -> str:
    ext_method = (
        source_model.ext.get("melix.quantization.method", "").strip().lower()
        or source_model.ext.get("quantization_method", "").strip().lower()
    )
    if ext_method:
        return ext_method

    profile_id = source_model.quant_profile_id.strip().lower()
    if profile_id and (
        profile_id in EXPLICIT_QUANTIZED_PROFILE_IDS
        or _QUANTIZED_MODEL_PATTERN.search(profile_id) is not None
    ):
        return "quant_profile"

    searchable = " ".join(
        [
            source_model.model_id.lower(),
            source_model.model_path.lower(),
            source_model.revision.lower(),
        ]
    )
    if _QUANTIZED_MODEL_PATTERN.search(searchable) is not None:
        return "path_hint"
    return ""


def _validate_quantization_provider(
    source_model: common_pb2.ModelSpec,
    *,
    base_quantization_method: str,
) -> None:
    if base_quantization_method in _BUILTIN_QUANTIZATION_METHODS:
        return
    provider = (
        source_model.ext.get("melix.quantization.provider", "").strip()
        or source_model.ext.get("quantization_provider", "").strip()
    )
    if provider:
        return
    raise ModelOperationError(
        code=UNSUPPORTED_REASON_MISSING_QUANTIZATION_PROVIDER,
        message=f"No quantization provider is registered for {base_quantization_method}.",
        details={"base_quantization_method": base_quantization_method},
    )


def _int_value(raw_value: str, *, default: int, minimum: int, field_name: str) -> int:
    try:
        value = default if not raw_value else int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ModelOperationError(
            code="invalid_argument",
            message=f"{field_name} must be an integer.",
            details={"field": field_name, "raw_value": str(raw_value)},
        ) from exc
    if value < minimum:
        raise ModelOperationError(
            code="invalid_argument",
            message=f"{field_name} must be at least {minimum}.",
            details={"field": field_name, "minimum": str(minimum)},
        )
    return value


def _float_value(raw_value: str, *, default: float, minimum: float, field_name: str) -> float:
    try:
        value = default if not raw_value else float(raw_value)
    except (TypeError, ValueError) as exc:
        raise ModelOperationError(
            code="invalid_argument",
            message=f"{field_name} must be a number.",
            details={"field": field_name, "raw_value": str(raw_value)},
        ) from exc
    if value < minimum:
        raise ModelOperationError(
            code="invalid_argument",
            message=f"{field_name} must be at least {minimum}.",
            details={"field": field_name, "minimum": str(minimum)},
        )
    return value


def _bool_value(raw_value: str, *, default: bool) -> bool:
    if not raw_value:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}
