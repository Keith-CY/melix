from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class QuantizedTensorMetadata:
    tensor_to_shard: Mapping[str, str]
    _tensor_names: frozenset[str] = field(default_factory=frozenset, init=False, repr=False)

    def __post_init__(self) -> None:
        normalized: dict[str, str] = {}
        for raw_name, raw_shard in self.tensor_to_shard.items():
            name = str(raw_name)
            if name:
                normalized[name] = str(raw_shard)
        object.__setattr__(
            self,
            "tensor_to_shard",
            MappingProxyType(normalized),
        )
        object.__setattr__(self, "_tensor_names", frozenset(normalized))

    @property
    def tensor_names(self) -> frozenset[str]:
        return self._tensor_names

    def has_tensor(self, tensor_name: str) -> bool:
        return tensor_name in self._tensor_names

    def shard_for(self, tensor_name: str) -> str:
        return self.tensor_to_shard.get(tensor_name, "")

    def quantized_tensor_shards(self, prefix: str) -> dict[str, str]:
        shards: dict[str, str] = {}
        weight_shard = self.shard_for(f"{prefix}.weight")
        scales_shard = self.shard_for(f"{prefix}.scales")
        if weight_shard:
            shards["weight"] = weight_shard
        if scales_shard:
            shards["scales"] = scales_shard
        return shards

    def has_quantized_scales(self, prefix: str) -> bool:
        return self.has_tensor(f"{prefix}.scales")


EMPTY_QUANTIZED_TENSOR_METADATA = QuantizedTensorMetadata({})
MAX_SAFETENSORS_HEADER_BYTES = 100 * 1024 * 1024


def _metadata_from_normalized_mapping(tensor_to_shard: dict[str, str]) -> QuantizedTensorMetadata:
    if not tensor_to_shard:
        return EMPTY_QUANTIZED_TENSOR_METADATA
    metadata = object.__new__(QuantizedTensorMetadata)
    object.__setattr__(metadata, "tensor_to_shard", MappingProxyType(tensor_to_shard))
    object.__setattr__(metadata, "_tensor_names", frozenset(tensor_to_shard))
    return metadata


_NATIVE_MULTIMODAL_HIGH_PRECISION_PREFIXES = (
    "audio_tower",
    "embed_audio",
    "embed_vision",
    "multi_modal_projector",
    "multimodal_projector",
    "projector",
    "vision_model",
    "vision_projector",
    "vision_tower",
    "visual",
)
_NATIVE_MULTIMODAL_HIGH_PRECISION_SUFFIXES = (
    ".lm_head",
    ".output",
    ".output_layer",
    ".score",
)
_NATIVE_MULTIMODAL_HIGH_PRECISION_SEGMENTS = frozenset(_NATIVE_MULTIMODAL_HIGH_PRECISION_PREFIXES)
_NATIVE_MULTIMODAL_HIGH_PRECISION_OUTPUT_SEGMENTS = frozenset(
    suffix[1:] for suffix in _NATIVE_MULTIMODAL_HIGH_PRECISION_SUFFIXES
)
_NATIVE_MULTIMODAL_HIGH_PRECISION_DIRECT_SEGMENTS = (
    _NATIVE_MULTIMODAL_HIGH_PRECISION_SEGMENTS
    | _NATIVE_MULTIMODAL_HIGH_PRECISION_OUTPUT_SEGMENTS
)
_NATIVE_MULTIMODAL_HIGH_PRECISION_DIRECT_PREFIXES = tuple(
    f"{segment}." for segment in _NATIVE_MULTIMODAL_HIGH_PRECISION_DIRECT_SEGMENTS
)
_NATIVE_MULTIMODAL_CONTAINER_SEGMENTS = frozenset(("model", "language_model"))
_NATIVE_MULTIMODAL_CONTAINER_HIGH_PRECISION_EXACT_PREFIXES = frozenset(
    f"{container}.{segment}"
    for container in _NATIVE_MULTIMODAL_CONTAINER_SEGMENTS
    for segment in _NATIVE_MULTIMODAL_HIGH_PRECISION_DIRECT_SEGMENTS
)
_NATIVE_MULTIMODAL_CONTAINER_HIGH_PRECISION_DIRECT_PREFIXES = tuple(
    f"{prefix}." for prefix in _NATIVE_MULTIMODAL_CONTAINER_HIGH_PRECISION_EXACT_PREFIXES
)


def _load_json_payload(path: Path) -> dict[str, Any]:
    try:
        with open(path, "rb") as payload_file:
            payload = json.loads(payload_file.read())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def quantized_tensor_metadata_from_index_payload(
    index_payload: Mapping[str, object] | None,
) -> QuantizedTensorMetadata:
    weight_map = index_payload.get("weight_map") if isinstance(index_payload, Mapping) else None
    if not isinstance(weight_map, Mapping):
        return EMPTY_QUANTIZED_TENSOR_METADATA
    tensor_to_shard: dict[str, str] = {}
    for raw_tensor_name, raw_shard_name in weight_map.items():
        tensor_name = str(raw_tensor_name)
        if tensor_name:
            tensor_to_shard[tensor_name] = str(raw_shard_name)
    return _metadata_from_normalized_mapping(tensor_to_shard)


def quantized_tensor_metadata_from_safetensor_headers(
    shard_paths: Sequence[str | os.PathLike[str]],
) -> QuantizedTensorMetadata:
    tensor_to_shard: dict[str, str] = {}
    for raw_path in shard_paths:
        shard_name = os.fspath(raw_path)
        for tensor_name in _safetensors_header_tensor_names(shard_name):
            tensor_to_shard[tensor_name] = shard_name
    if not tensor_to_shard:
        return EMPTY_QUANTIZED_TENSOR_METADATA
    return _metadata_from_normalized_mapping(tensor_to_shard)


def quantized_tensor_metadata_from_model_dir(
    model_path: Path,
    *,
    weight_files: Sequence[str | os.PathLike[str]] = (),
    extra_files: Sequence[str | os.PathLike[str]] = (),
    index_payload: Mapping[str, object] | None = None,
) -> QuantizedTensorMetadata:
    payload = index_payload
    if payload is None:
        payload = _load_json_payload(model_path / "model.safetensors.index.json")
    metadata = quantized_tensor_metadata_from_index_payload(payload)
    if metadata.tensor_to_shard:
        return metadata

    shard_paths: list[str | os.PathLike[str]] = [*weight_files, *extra_files]
    if not shard_paths:
        try:
            with os.scandir(model_path) as entries:
                for entry in entries:
                    try:
                        if entry.name.endswith(".safetensors") and entry.is_file():
                            shard_paths.append(entry.path)
                    except OSError:
                        continue
        except OSError:
            return EMPTY_QUANTIZED_TENSOR_METADATA
    return quantized_tensor_metadata_from_safetensor_headers(shard_paths)


def cross_shard_quantized_metadata_fixup_count(
    metadata: QuantizedTensorMetadata,
) -> int:
    weights: dict[str, str] = {}
    scales: dict[str, str] = {}
    for tensor_name, shard_name in metadata.tensor_to_shard.items():
        if tensor_name.endswith(".weight"):
            weights[tensor_name[: -len(".weight")]] = shard_name
        elif tensor_name.endswith(".scales"):
            scales[tensor_name[: -len(".scales")]] = shard_name

    if len(weights) < len(scales):
        return sum(
            1
            for prefix, weight_shard in weights.items()
            if (scales_shard := scales.get(prefix, "")) and weight_shard != scales_shard
        )
    return sum(
        1
        for prefix, scales_shard in scales.items()
        if (weight_shard := weights.get(prefix, "")) and weight_shard != scales_shard
    )


def quantized_scales_present(
    prefix: str,
    *,
    metadata: QuantizedTensorMetadata,
    weights: Mapping[str, object],
) -> bool:
    scales_key = f"{prefix}.scales"
    if scales_key in metadata._tensor_names:
        return True
    if not weights:
        return False
    return scales_key in weights


def native_multimodal_quantization_preserves_precision(
    prefix: str,
    *,
    metadata: QuantizedTensorMetadata,
    weights: Mapping[str, object],
) -> bool:
    """Return whether native multimodal quantization should keep a module high precision.

    Vision towers, multimodal projectors, and output heads often need the dtype
    they were exported with. They are only safe to quantize when the artifact
    explicitly includes quantized scale metadata for that module.
    """

    normalized = str(prefix or "").strip()
    if not normalized:
        return False
    if not _native_multimodal_high_precision_module(normalized):
        return False
    return not quantized_scales_present(
        normalized,
        metadata=metadata,
        weights=weights,
    )


def _native_multimodal_high_precision_module(prefix: str) -> bool:
    if (
        "vision" not in prefix
        and "visual" not in prefix
        and "projector" not in prefix
        and "lm_head" not in prefix
        and "output" not in prefix
        and "score" not in prefix
    ):
        return False
    direct_segments = _NATIVE_MULTIMODAL_HIGH_PRECISION_DIRECT_SEGMENTS
    if prefix in direct_segments or prefix.startswith(
        _NATIVE_MULTIMODAL_HIGH_PRECISION_DIRECT_PREFIXES
    ):
        return True
    container_prefixes = _NATIVE_MULTIMODAL_CONTAINER_HIGH_PRECISION_EXACT_PREFIXES
    if prefix in container_prefixes or prefix.startswith(
        _NATIVE_MULTIMODAL_CONTAINER_HIGH_PRECISION_DIRECT_PREFIXES
    ):
        return True
    start = 0
    prefix_length = len(prefix)
    previous_segment = ""
    while start <= prefix_length:
        separator_index = prefix.find(".", start)
        if separator_index < 0:
            segment = prefix[start:]
            start = prefix_length + 1
        else:
            segment = prefix[start:separator_index]
            start = separator_index + 1
        if not segment:
            continue
        if segment in _NATIVE_MULTIMODAL_HIGH_PRECISION_SEGMENTS:
            return True
        if (
            previous_segment in _NATIVE_MULTIMODAL_CONTAINER_SEGMENTS
            and segment in _NATIVE_MULTIMODAL_HIGH_PRECISION_SEGMENTS
        ):
            return True
        if segment in _NATIVE_MULTIMODAL_HIGH_PRECISION_OUTPUT_SEGMENTS:
            return True
        previous_segment = segment
    return False


def _safetensors_header_tensor_names(path: str | os.PathLike[str]) -> tuple[str, ...]:
    try:
        with open(path, "rb") as handle:
            header_size_raw = handle.read(8)
            if len(header_size_raw) != 8:
                return ()
            header_size = int.from_bytes(header_size_raw, "little")
            if header_size <= 0 or header_size > MAX_SAFETENSORS_HEADER_BYTES:
                return ()
            header_payload = handle.read(header_size)
    except OSError:
        return ()
    try:
        header = json.loads(header_payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ()
    if not isinstance(header, dict):
        return ()
    tensor_names: list[str] = []
    append_tensor_name = tensor_names.append
    for key in header:
        if key == "__metadata__":
            continue
        if isinstance(key, str):
            if key:
                append_tensor_name(key)
            continue
        tensor_name = str(key)
        if tensor_name:
            append_tensor_name(tensor_name)
    return tuple(tensor_names)
