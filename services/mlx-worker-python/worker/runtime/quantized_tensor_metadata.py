from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class QuantizedTensorMetadata:
    tensor_to_shard: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "tensor_to_shard",
            MappingProxyType(
                {
                    str(name): str(shard)
                    for name, shard in self.tensor_to_shard.items()
                    if str(name)
                }
            ),
        )

    @property
    def tensor_names(self) -> frozenset[str]:
        return frozenset(self.tensor_to_shard)

    def has_tensor(self, tensor_name: str) -> bool:
        return tensor_name in self.tensor_to_shard

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


def _load_json_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_bytes())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def quantized_tensor_metadata_from_index_payload(
    index_payload: Mapping[str, object] | None,
) -> QuantizedTensorMetadata:
    weight_map = index_payload.get("weight_map") if isinstance(index_payload, Mapping) else None
    if not isinstance(weight_map, Mapping):
        return EMPTY_QUANTIZED_TENSOR_METADATA
    return QuantizedTensorMetadata(
        {
            str(tensor_name): str(shard_name)
            for tensor_name, shard_name in weight_map.items()
            if str(tensor_name)
        }
    )


def quantized_tensor_metadata_from_safetensor_headers(
    shard_paths: Sequence[str | os.PathLike[str]],
) -> QuantizedTensorMetadata:
    tensor_to_shard: dict[str, str] = {}
    for raw_path in shard_paths:
        path = Path(raw_path)
        shard_name = os.fspath(raw_path)
        for tensor_name in _safetensors_header_tensor_names(path):
            tensor_to_shard[tensor_name] = shard_name
    if not tensor_to_shard:
        return EMPTY_QUANTIZED_TENSOR_METADATA
    return QuantizedTensorMetadata(tensor_to_shard)


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


def quantized_scales_present(
    prefix: str,
    *,
    metadata: QuantizedTensorMetadata,
    weights: Mapping[str, object],
) -> bool:
    scales_key = f"{prefix}.scales"
    return metadata.has_tensor(scales_key) or scales_key in weights


def _safetensors_header_tensor_names(path: Path) -> tuple[str, ...]:
    try:
        with path.open("rb") as handle:
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
    return tuple(
        str(key)
        for key in header
        if key != "__metadata__" and str(key)
    )
