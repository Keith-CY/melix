from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import struct
from typing import Any, Iterable, Mapping, Sequence

from worker.model_ops.errors import ModelOperationError


_FINITE_MASK_FLOORS = {
    "float16": -1.0e4,
    "bfloat16": -1.0e4,
    "float32": -1.0e9,
    "float64": -1.0e30,
}
_TENSOR_DTYPE_BYTES = {
    "BOOL": 1,
    "U8": 1,
    "I8": 1,
    "F8_E4M3": 1,
    "F8_E5M2": 1,
    "I16": 2,
    "U16": 2,
    "F16": 2,
    "BF16": 2,
    "I32": 4,
    "U32": 4,
    "F32": 4,
    "I64": 8,
    "U64": 8,
    "F64": 8,
}
_DISALLOWED_COMPONENT_PREFIXES = {
    "vision_tower": "vision_encoder",
    "vision_model": "vision_encoder",
    "visual": "vision_encoder",
    "embed_vision": "vision_encoder",
    "multi_modal_projector": "multimodal_projector",
    "multimodal_projector": "multimodal_projector",
    "mm_projector": "multimodal_projector",
    "audio_tower": "audio_encoder",
    "audio_model": "audio_encoder",
    "embed_audio": "audio_encoder",
    "model.embed_tokens": "embedding",
    "language_model.model.embed_tokens": "embedding",
    "text_model.embed_tokens": "embedding",
    "embed_tokens": "embedding",
    "lm_head": "embedding",
    "output_head": "embedding",
    "output_projection": "embedding",
}
_TRAINABLE_ADAPTER_TOKENS = (
    ".lora_a",
    ".lora_b",
    ".m",
    ".magnitude",
    "lora_a",
    "lora_b",
    "magnitude",
)
_MAX_SAFETENSORS_HEADER_BYTES = 8 * 1024 * 1024
_SAFETENSORS_HEADER_READ_CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True)
class FiniteAttentionMask:
    additive_mask: list[Any]
    finite_floor: float
    all_masked_row_count: int

    @property
    def nan_guard_triggered(self) -> bool:
        return self.all_masked_row_count > 0


@dataclass(frozen=True)
class AdapterFreezeAudit:
    adapter_checkpoint_bytes: int
    expected_lora_checkpoint_bytes: int
    adapter_checkpoint_size_ratio: float
    adapter_checkpoint_size_within_target: bool
    unexpected_frozen_param_count: int
    unexpected_trainable_param_count: int
    unexpected_serialized_param_count: int
    serialized_param_count_by_component: dict[str, int]
    trainable_param_count_by_component: dict[str, int]
    unexpected_serialized_parameters: tuple[str, ...]
    unexpected_trainable_parameters: tuple[str, ...]
    multimodal_lora_nan_guard_triggered: bool = False
    unexpected_serialized_param_counts: dict[str, int] | None = None
    unexpected_trainable_param_counts: dict[str, int] | None = None


def dtype_safe_finite_mask_floor(dtype: object = None) -> float:
    dtype_name = str(dtype or "float32").lower()
    for key, value in _FINITE_MASK_FLOORS.items():
        if key in dtype_name:
            return value
    return _FINITE_MASK_FLOORS["float32"]


def finite_attention_mask(
    visible_mask: Sequence[Any],
    *,
    dtype: object = None,
) -> FiniteAttentionMask:
    """Convert a bool attention mask to a finite additive mask.

    The returned mask uses ``0`` for visible positions and a dtype-safe finite
    negative floor for masked positions. Fully masked rows are counted so the
    training receipt can prove the NaN guard was exercised.
    """

    floor = dtype_safe_finite_mask_floor(dtype)
    all_masked_rows = 0

    def convert(node: Any) -> Any:
        nonlocal all_masked_rows
        if _is_sequence(node) and node and all(not _is_sequence(item) for item in node):
            row = [bool(item) for item in node]
            if not any(row):
                all_masked_rows += 1
            return [0.0 if item else floor for item in row]
        if _is_sequence(node):
            return [convert(item) for item in node]
        keep = bool(node)
        if not keep:
            all_masked_rows += 1
        return 0.0 if keep else floor

    return FiniteAttentionMask(
        additive_mask=convert(visible_mask),
        finite_floor=floor,
        all_masked_row_count=all_masked_rows,
    )


def finite_masked_softmax(
    scores: Sequence[Any],
    visible_mask: Sequence[Any],
    *,
    dtype: object = None,
) -> tuple[list[Any], FiniteAttentionMask]:
    mask = finite_attention_mask(visible_mask, dtype=dtype)

    def apply(score_node: Any, mask_node: Any, visible_node: Any) -> Any:
        if _is_sequence(score_node) and score_node and all(not _is_sequence(item) for item in score_node):
            scored_row = [float(score) + float(mask_value) for score, mask_value in zip(score_node, mask_node)]
            visible_row = [bool(item) for item in visible_node]
            if not any(visible_row):
                return [0.0 for _ in scored_row]
            row_max = max(scored_row) if scored_row else 0.0
            exps = [
                math.exp(value - row_max) if visible else 0.0
                for value, visible in zip(scored_row, visible_row)
            ]
            total = sum(exps)
            if total <= 0.0:
                return [0.0 for _ in scored_row]
            return [value / total for value in exps]
        if _is_sequence(score_node):
            return [
                apply(child_score, child_mask, child_visible)
                for child_score, child_mask, child_visible in zip(score_node, mask_node, visible_node)
            ]
        if not bool(visible_node):
            return 0.0
        return 1.0

    return apply(scores, mask.additive_mask, visible_mask), mask


def audit_trainable_module_tree(
    model: Any,
    *,
    allowed_target_modules: Iterable[str],
    source_model_kind: str,
    source_model_ext: Mapping[str, str] | None = None,
) -> AdapterFreezeAudit:
    del source_model_kind
    del source_model_ext
    allowed_fragments = _normalized_target_fragments(allowed_target_modules)
    trainable_counts: dict[str, int] = {}
    unexpected_names: list[str] = []
    unexpected_counts: dict[str, int] = {}
    unexpected_count = 0
    for name, parameter in _iter_trainable_parameters(model):
        count = _parameter_count(parameter)
        component = _component_for_parameter_name(name)
        trainable_counts[component] = trainable_counts.get(component, 0) + count
        if _is_unexpected_adapter_parameter(name, allowed_fragments):
            unexpected_names.append(name)
            unexpected_counts[name] = unexpected_counts.get(name, 0) + count
            unexpected_count += count

    return AdapterFreezeAudit(
        adapter_checkpoint_bytes=0,
        expected_lora_checkpoint_bytes=0,
        adapter_checkpoint_size_ratio=1.0,
        adapter_checkpoint_size_within_target=True,
        unexpected_frozen_param_count=unexpected_count,
        unexpected_trainable_param_count=unexpected_count,
        unexpected_serialized_param_count=0,
        serialized_param_count_by_component={},
        trainable_param_count_by_component=trainable_counts,
        unexpected_serialized_parameters=(),
        unexpected_trainable_parameters=tuple(unexpected_names),
        unexpected_trainable_param_counts=unexpected_counts,
    )


def audit_adapter_checkpoint(
    *,
    weights_path: Path,
    allowed_target_modules: Iterable[str],
    source_model_kind: str,
    source_model_ext: Mapping[str, str] | None = None,
    live_audit: AdapterFreezeAudit | Mapping[str, Any] | None = None,
    multimodal_lora_nan_guard_triggered: bool = False,
) -> AdapterFreezeAudit:
    del source_model_kind
    del source_model_ext
    checkpoint_bytes = weights_path.stat().st_size if weights_path.is_file() else 0
    allowed_fragments = _normalized_target_fragments(allowed_target_modules)
    tensors = _read_safetensors_header(weights_path)
    serialized_counts: dict[str, int] = {}
    unexpected_serialized_names: list[str] = []
    unexpected_serialized_counts: dict[str, int] = {}
    unexpected_serialized_count = 0
    unexpected_serialized_bytes = 0
    total_tensor_bytes = 0
    for name, metadata in tensors.items():
        count = _safetensors_parameter_count(metadata)
        tensor_bytes = _safetensors_tensor_bytes(metadata)
        total_tensor_bytes += tensor_bytes
        component = _component_for_parameter_name(name)
        serialized_counts[component] = serialized_counts.get(component, 0) + count
        if _is_unexpected_adapter_parameter(name, allowed_fragments):
            unexpected_serialized_names.append(name)
            unexpected_serialized_counts[name] = unexpected_serialized_counts.get(name, 0) + count
            unexpected_serialized_count += count
            unexpected_serialized_bytes += tensor_bytes

    unexpected_trainable_count = 0
    unexpected_trainable_names: tuple[str, ...] = ()
    unexpected_trainable_counts: dict[str, int] = {}
    trainable_counts: Mapping[str, int] = {}
    if isinstance(live_audit, AdapterFreezeAudit):
        unexpected_trainable_count = live_audit.unexpected_trainable_param_count
        unexpected_trainable_names = live_audit.unexpected_trainable_parameters
        unexpected_trainable_counts = dict(live_audit.unexpected_trainable_param_counts or {})
        trainable_counts = live_audit.trainable_param_count_by_component
    elif isinstance(live_audit, Mapping):
        unexpected_trainable_count = _int_mapping_value(live_audit, "unexpected_trainable_param_count")
        unexpected_names = live_audit.get("unexpected_trainable_parameters", ())
        if isinstance(unexpected_names, Sequence) and not isinstance(unexpected_names, (str, bytes, bytearray)):
            unexpected_trainable_names = tuple(str(item) for item in unexpected_names)
        unexpected_trainable_counts = _int_dict(live_audit.get("unexpected_trainable_param_counts", {}))
        raw_counts = live_audit.get("trainable_param_count_by_component", {})
        if isinstance(raw_counts, Mapping):
            trainable_counts = {str(key): int(value) for key, value in raw_counts.items()}
    expected_checkpoint_bytes = checkpoint_bytes
    if unexpected_serialized_bytes > 0:
        expected_checkpoint_bytes = max(1, checkpoint_bytes - unexpected_serialized_bytes)
    elif total_tensor_bytes > 0:
        expected_checkpoint_bytes = checkpoint_bytes
    size_ratio = 1.0 if expected_checkpoint_bytes <= 0 else checkpoint_bytes / expected_checkpoint_bytes
    unexpected_total_count = _combined_unexpected_param_count(
        serialized_counts=unexpected_serialized_counts,
        trainable_counts=unexpected_trainable_counts,
        serialized_total=unexpected_serialized_count,
        trainable_total=unexpected_trainable_count,
    )
    return AdapterFreezeAudit(
        adapter_checkpoint_bytes=checkpoint_bytes,
        expected_lora_checkpoint_bytes=expected_checkpoint_bytes,
        adapter_checkpoint_size_ratio=size_ratio,
        adapter_checkpoint_size_within_target=size_ratio <= 1.2,
        unexpected_frozen_param_count=unexpected_total_count,
        unexpected_trainable_param_count=unexpected_trainable_count,
        unexpected_serialized_param_count=unexpected_serialized_count,
        serialized_param_count_by_component=serialized_counts,
        trainable_param_count_by_component=dict(trainable_counts),
        unexpected_serialized_parameters=tuple(unexpected_serialized_names),
        unexpected_trainable_parameters=unexpected_trainable_names,
        multimodal_lora_nan_guard_triggered=multimodal_lora_nan_guard_triggered,
        unexpected_serialized_param_counts=unexpected_serialized_counts,
        unexpected_trainable_param_counts=unexpected_trainable_counts,
    )


def raise_for_adapter_freeze_audit(audit: AdapterFreezeAudit) -> None:
    if audit.unexpected_frozen_param_count <= 0 and audit.adapter_checkpoint_size_within_target:
        return
    raise ModelOperationError(
        code="adapter_freeze_audit_failed",
        message="LoRA adapter export contains parameters outside the intended trainable surface.",
        details={
            "unexpected_frozen_param_count": str(audit.unexpected_frozen_param_count),
            "unexpected_trainable_param_count": str(audit.unexpected_trainable_param_count),
            "unexpected_serialized_param_count": str(audit.unexpected_serialized_param_count),
            "adapter_checkpoint_bytes": str(audit.adapter_checkpoint_bytes),
            "expected_lora_checkpoint_bytes": str(audit.expected_lora_checkpoint_bytes),
            "adapter_checkpoint_size_ratio": f"{audit.adapter_checkpoint_size_ratio:.6f}",
            "unexpected_serialized_parameters": ",".join(audit.unexpected_serialized_parameters),
            "unexpected_trainable_parameters": ",".join(audit.unexpected_trainable_parameters),
        },
    )


def audit_manifest_fields(audit: AdapterFreezeAudit) -> dict[str, Any]:
    return {
        "multimodal_lora_nan_guard_triggered": audit.multimodal_lora_nan_guard_triggered,
        "unexpected_frozen_param_count": audit.unexpected_frozen_param_count,
        "adapter_checkpoint_bytes": audit.adapter_checkpoint_bytes,
        "adapter_freeze_audit": {
            "unexpected_trainable_param_count": audit.unexpected_trainable_param_count,
            "unexpected_serialized_param_count": audit.unexpected_serialized_param_count,
            "trainable_param_count_by_component": audit.trainable_param_count_by_component,
            "serialized_param_count_by_component": audit.serialized_param_count_by_component,
            "unexpected_trainable_parameters": list(audit.unexpected_trainable_parameters),
            "unexpected_serialized_parameters": list(audit.unexpected_serialized_parameters),
            "unexpected_trainable_param_counts": dict(audit.unexpected_trainable_param_counts or {}),
            "unexpected_serialized_param_counts": dict(audit.unexpected_serialized_param_counts or {}),
            "expected_lora_checkpoint_bytes": audit.expected_lora_checkpoint_bytes,
            "adapter_checkpoint_size_ratio": audit.adapter_checkpoint_size_ratio,
            "adapter_checkpoint_size_within_target": audit.adapter_checkpoint_size_within_target,
        },
        "training.multimodal_lora_nan_guard_triggered": audit.multimodal_lora_nan_guard_triggered,
        "training.unexpected_frozen_param_count": audit.unexpected_frozen_param_count,
        "training.adapter_checkpoint_bytes": audit.adapter_checkpoint_bytes,
    }


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _normalized_target_fragments(target_modules: Iterable[str]) -> tuple[str, ...]:
    fragments: list[str] = []
    for target in target_modules:
        normalized = _normalize_parameter_name(str(target))
        if not normalized:
            continue
        fragments.append(normalized)
        fragments.append(normalized.removeprefix("model."))
        fragments.append(normalized.removeprefix("language_model."))
    return tuple(dict.fromkeys(fragment for fragment in fragments if fragment))


def _is_unexpected_adapter_parameter(name: str, allowed_fragments: tuple[str, ...]) -> bool:
    normalized = _normalize_parameter_name(name)
    if _component_for_parameter_name(normalized) in {
        "vision_encoder",
        "multimodal_projector",
        "audio_encoder",
        "embedding",
    }:
        return True
    adapter_owned = any(token in normalized for token in _TRAINABLE_ADAPTER_TOKENS)
    if not allowed_fragments:
        return not adapter_owned
    if not adapter_owned:
        return True
    return not any(fragment in normalized for fragment in allowed_fragments)


def _component_for_parameter_name(name: str) -> str:
    normalized = _normalize_parameter_name(name)
    for prefix, component in _DISALLOWED_COMPONENT_PREFIXES.items():
        if normalized == prefix or normalized.startswith(f"{prefix}."):
            return component
    if normalized.startswith("language_model.") or normalized.startswith("model.layers."):
        return "text_backbone"
    first = normalized.split(".", 1)[0]
    return first or "unknown"


def _normalize_parameter_name(name: str) -> str:
    normalized = name.replace("/", ".").replace("..", ".").strip(".").lower()
    for prefix in ("base_model.", "model.model."):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
    return normalized


def _iter_trainable_parameters(model: Any) -> Iterable[tuple[str, Any]]:
    trainable_parameters = getattr(model, "trainable_parameters", None)
    if callable(trainable_parameters):
        yield from _flatten_parameter_tree(trainable_parameters())
        return
    named_parameters = getattr(model, "named_parameters", None)
    if callable(named_parameters):
        for item in named_parameters():
            try:
                name, parameter = item
            except (TypeError, ValueError):
                continue
            requires_grad = getattr(parameter, "requires_grad", None)
            if requires_grad is False:
                continue
            yield str(name), parameter


def _flatten_parameter_tree(node: Any, prefix: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(node, Mapping):
        for key, value in node.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            yield from _flatten_parameter_tree(value, child_prefix)
        return
    if isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            child_prefix = f"{prefix}.{index}" if prefix else str(index)
            yield from _flatten_parameter_tree(value, child_prefix)
        return
    if prefix:
        yield prefix, node


def _parameter_count(parameter: Any) -> int:
    size = getattr(parameter, "size", None)
    if isinstance(size, int) and size >= 0:
        return size
    shape = getattr(parameter, "shape", None)
    if isinstance(shape, Sequence):
        count = 1
        for dimension in shape:
            count *= max(0, int(dimension))
        return count
    try:
        return len(parameter)
    except TypeError:
        return 1


def _combined_unexpected_param_count(
    *,
    serialized_counts: Mapping[str, int],
    trainable_counts: Mapping[str, int],
    serialized_total: int,
    trainable_total: int,
) -> int:
    if serialized_counts or trainable_counts:
        names = set(serialized_counts) | set(trainable_counts)
        return sum(
            max(
                int(serialized_counts.get(name, 0)),
                int(trainable_counts.get(name, 0)),
            )
            for name in names
        )
    if serialized_total > 0 and trainable_total > 0:
        return max(serialized_total, trainable_total)
    return serialized_total + trainable_total


def _read_safetensors_header(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    try:
        file_size = path.stat().st_size
        with path.open("rb") as handle:
            raw_size = handle.read(8)
            if len(raw_size) != 8:
                return {}
            header_size = struct.unpack("<Q", raw_size)[0]
            if (
                header_size <= 0
                or header_size > _MAX_SAFETENSORS_HEADER_BYTES
                or header_size > max(0, file_size - 8)
            ):
                return {}
            remaining = header_size
            chunks = bytearray()
            while remaining > 0:
                chunk = handle.read(min(_SAFETENSORS_HEADER_READ_CHUNK_BYTES, remaining))
                if not chunk:
                    return {}
                chunks.extend(chunk)
                remaining -= len(chunk)
            header = json.loads(chunks.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, struct.error):
        return {}
    if not isinstance(header, dict):
        return {}
    tensors: dict[str, dict[str, Any]] = {}
    for key, value in header.items():
        if key == "__metadata__" or not isinstance(value, dict):
            continue
        tensors[str(key)] = value
    return tensors


def _safetensors_parameter_count(metadata: Mapping[str, Any]) -> int:
    shape = metadata.get("shape", [])
    if not isinstance(shape, Sequence):
        return 0
    count = 1
    for dimension in shape:
        count *= max(0, int(dimension))
    return count


def _safetensors_tensor_bytes(metadata: Mapping[str, Any]) -> int:
    offsets = metadata.get("data_offsets")
    if isinstance(offsets, Sequence) and len(offsets) == 2:
        try:
            start = int(offsets[0])
            end = int(offsets[1])
        except (TypeError, ValueError):
            start = end = 0
        if end >= start:
            return end - start
    dtype = str(metadata.get("dtype", "")).upper()
    return _safetensors_parameter_count(metadata) * _TENSOR_DTYPE_BYTES.get(dtype, 0)


def _int_mapping_value(payload: Mapping[str, Any], key: str) -> int:
    try:
        return int(payload.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _int_dict(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    converted: dict[str, int] = {}
    for key, raw_count in value.items():
        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            continue
        if count >= 0:
            converted[str(key)] = count
    return converted
