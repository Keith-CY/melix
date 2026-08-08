#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
import tracemalloc
from dataclasses import dataclass
from typing import Callable, Mapping, cast

repo_root_env = os.environ.get("MELIX_QUANTIZED_TENSOR_METADATA_REPO_ROOT")
REPO_ROOT = Path(repo_root_env) if repo_root_env else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

try:
    from worker.runtime.quantized_tensor_metadata import (  # noqa: E402
        QuantizedTensorMetadata,
        _native_multimodal_high_precision_module,
        cross_shard_quantized_metadata_fixup_count,
        quantized_scales_present,
        quantized_tensor_metadata_from_index_payload,
        quantized_tensor_metadata_from_safetensor_headers,
    )
except ImportError:  # Base refs before the metadata prepass do not have the helper module.
    @dataclass
    class QuantizedTensorMetadata:  # type: ignore[no-redef]
        tensor_to_shard: dict[str, str]

        def __post_init__(self) -> None:
            self.tensor_to_shard = {
                str(tensor_name): str(shard_name)
                for tensor_name, shard_name in self.tensor_to_shard.items()
                if str(tensor_name)
            }

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

    def quantized_tensor_metadata_from_index_payload(
        index_payload: Mapping[str, object] | None,
    ) -> QuantizedTensorMetadata:
        weight_map = index_payload.get("weight_map") if isinstance(index_payload, Mapping) else None
        if not isinstance(weight_map, Mapping):
            return QuantizedTensorMetadata({})
        return QuantizedTensorMetadata(
            {
                str(tensor_name): str(shard_name)
                for tensor_name, shard_name in weight_map.items()
                if str(tensor_name)
            }
        )

    def quantized_tensor_metadata_from_safetensor_headers(
        shard_paths: list[Path],
    ) -> QuantizedTensorMetadata:
        tensor_to_shard: dict[str, str] = {}
        for shard_path in shard_paths:
            with shard_path.open("rb") as handle:
                header_size = int.from_bytes(handle.read(8), "little")
                header = json.loads(handle.read(header_size))
            tensor_to_shard.update(
                {
                    str(tensor_name): str(shard_path)
                    for tensor_name in header
                    if tensor_name != "__metadata__" and str(tensor_name)
                }
            )
        return QuantizedTensorMetadata(tensor_to_shard)

    def quantized_scales_present(
        prefix: str,
        *,
        metadata: QuantizedTensorMetadata,
        weights: Mapping[str, object],
    ) -> bool:
        scales_key = f"{prefix}.scales"
        return metadata.has_quantized_scales(prefix) or scales_key in weights

    def _native_multimodal_high_precision_module(prefix: str) -> bool:
        segments = tuple(segment for segment in prefix.split(".") if segment)
        for index, segment in enumerate(segments):
            if segment in {"projector", "vision_tower", "visual"}:
                return True
            if (
                segment in {"model", "language_model"}
                and index + 1 < len(segments)
                and segments[index + 1] in {"projector", "vision_tower", "visual"}
            ):
                return True
            if segment in {"lm_head", "output", "output_layer", "score"}:
                return True
        return False

    def cross_shard_quantized_metadata_fixup_count(
        metadata: QuantizedTensorMetadata,
    ) -> int:
        prefixes: set[str] = set()
        for tensor_name in metadata.tensor_to_shard:
            if tensor_name.endswith(".weight"):
                prefixes.add(tensor_name[: -len(".weight")])
            elif tensor_name.endswith(".scales"):
                prefixes.add(tensor_name[: -len(".scales")])
        count = 0
        for prefix in prefixes:
            shards = metadata.quantized_tensor_shards(prefix)
            if (
                shards.get("weight")
                and shards.get("scales")
                and shards["weight"] != shards["scales"]
            ):
                count += 1
        return count


def _build_weight_map(pair_count: int, shard_count: int) -> dict[str, str]:
    weight_map: dict[str, str] = {}
    for index in range(pair_count):
        prefix = f"language_model.layers.{index}.q_proj"
        weight_map[f"{prefix}.weight"] = f"model-{index % shard_count:05d}.safetensors"
        weight_map[f"{prefix}.scales"] = f"model-{(index + 1) % shard_count:05d}.safetensors"
        weight_map[f"{prefix}.biases"] = f"model-{(index + 2) % shard_count:05d}.safetensors"
    return weight_map


def _write_fake_safetensors_header(path: Path, tensor_names: list[str]) -> None:
    header = {
        tensor_name: {
            "dtype": "F16",
            "shape": [1],
            "data_offsets": [0, 0],
        }
        for tensor_name in tensor_names
    }
    payload = json.dumps(header, sort_keys=True).encode("utf-8")
    path.write_bytes(len(payload).to_bytes(8, "little") + payload)


def _write_header_shards(root: Path, weight_map: Mapping[str, str]) -> list[Path]:
    by_shard: dict[str, list[str]] = {}
    for tensor_name, shard_name in weight_map.items():
        by_shard.setdefault(shard_name, []).append(tensor_name)
    shard_paths: list[Path] = []
    for shard_name, tensor_names in by_shard.items():
        shard_path = root / shard_name
        _write_fake_safetensors_header(shard_path, tensor_names)
        shard_paths.append(shard_path)
    return shard_paths


def _materialized_scales_present(
    prefix: str,
    *,
    weights: Mapping[str, object],
) -> bool:
    return f"{prefix}.scales" in weights


def _high_precision_prefixes(pair_count: int) -> list[str]:
    prefixes: list[str] = []
    variants = (
        "language_model.layers.{index}.q_proj",
        "vision_tower.patch_embed.{index}",
        "model.visual.patch_embed.{index}",
        "language_model.lm_head.{index}",
        "model.visualizer.patch_embed.{index}",
        "prevision_tower.patch_embed.{index}",
    )
    for index in range(pair_count):
        prefixes.append(variants[index % len(variants)].format(index=index))
    return prefixes


def _measure(
    callback: Callable[[], object],
    *,
    samples: int,
) -> tuple[list[float], list[float], object]:
    elapsed_ms: list[float] = []
    peak_bytes: list[float] = []
    result: object = None
    for _ in range(samples):
        tracemalloc.start()
        started = time.perf_counter()
        try:
            result = callback()
        finally:
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        elapsed_ms.append((time.perf_counter() - started) * 1000.0)
        peak_bytes.append(float(peak))
    return elapsed_ms, peak_bytes, result


def run_probe() -> dict[str, float]:
    pair_count = int(os.environ.get("MELIX_QUANTIZED_METADATA_PAIR_COUNT", "2000"))
    shard_count = int(os.environ.get("MELIX_QUANTIZED_METADATA_SHARD_COUNT", "16"))
    samples = int(os.environ.get("MELIX_QUANTIZED_METADATA_SAMPLES", "5"))
    decision_iterations = int(os.environ.get("MELIX_QUANTIZED_METADATA_DECISION_ITERATIONS", "20"))
    weight_map = _build_weight_map(pair_count, shard_count)
    index_payload = {"weight_map": weight_map}
    prefixes = [f"language_model.layers.{index}.q_proj" for index in range(pair_count)]
    high_precision_prefixes = _high_precision_prefixes(pair_count)

    index_ms, index_peaks, metadata = _measure(
        lambda: quantized_tensor_metadata_from_index_payload(index_payload),
        samples=samples,
    )
    metadata = cast(QuantizedTensorMetadata, metadata)
    metadata_tensor_count = float(len(metadata.tensor_names))
    cross_shard_pair_count = float(
        sum(1 for prefix in prefixes if _is_cross_shard_quantized_pair(metadata, prefix))
    )

    tensor_names_access_ms, tensor_names_access_peaks, tensor_names_access_count = _measure(
        lambda: sum(
            len(metadata.tensor_names)
            for _ in range(decision_iterations)
            for _prefix in prefixes
        ),
        samples=samples,
    )

    cross_shard_fixup_ms, cross_shard_fixup_peaks, cross_shard_fixup_count = _measure(
        lambda: sum(
            cross_shard_quantized_metadata_fixup_count(metadata)
            for _ in range(decision_iterations)
        ),
        samples=samples,
    )

    metadata_decision_ms, metadata_decision_peaks, metadata_decision_count = _measure(
        lambda: sum(
            int(quantized_scales_present(prefix, metadata=metadata, weights={}))  # type: ignore[arg-type]
            for _ in range(decision_iterations)
            for prefix in prefixes
        ),
        samples=samples,
    )
    weights = {f"{prefix}.scales": object() for prefix in prefixes}
    materialized_decision_ms, materialized_decision_peaks, materialized_decision_count = _measure(
        lambda: sum(
            int(_materialized_scales_present(prefix, weights=weights))
            for _ in range(decision_iterations)
            for prefix in prefixes
        ),
        samples=samples,
    )
    if metadata_decision_count != materialized_decision_count:
        raise SystemExit("metadata quantized decisions differ from materialized weights")

    cache_clear = getattr(_native_multimodal_high_precision_module, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()
    for prefix in high_precision_prefixes:
        _native_multimodal_high_precision_module(prefix)

    high_precision_ms, high_precision_peaks, high_precision_decision_count = _measure(
        lambda: sum(
            int(_native_multimodal_high_precision_module(prefix))
            for _ in range(decision_iterations)
            for prefix in high_precision_prefixes
        ),
        samples=samples,
    )

    with tempfile.TemporaryDirectory(prefix="melix-quantized-metadata-") as tmp_dir:
        shard_paths = _write_header_shards(Path(tmp_dir), weight_map)
        header_ms, header_peaks, header_metadata = _measure(
            lambda: quantized_tensor_metadata_from_safetensor_headers(shard_paths),
            samples=samples,
        )
    header_metadata = cast(QuantizedTensorMetadata, header_metadata)

    return {
        "index_elapsed_ms_mean": statistics.fmean(index_ms),
        "index_peak_bytes_mean": statistics.fmean(index_peaks),
        "header_elapsed_ms_mean": statistics.fmean(header_ms),
        "header_peak_bytes_mean": statistics.fmean(header_peaks),
        "metadata_decision_elapsed_ms_mean": statistics.fmean(metadata_decision_ms),
        "metadata_decision_peak_bytes_mean": statistics.fmean(metadata_decision_peaks),
        "materialized_decision_elapsed_ms_mean": statistics.fmean(materialized_decision_ms),
        "materialized_decision_peak_bytes_mean": statistics.fmean(materialized_decision_peaks),
        "high_precision_decision_elapsed_ms_mean": statistics.fmean(high_precision_ms),
        "high_precision_decision_peak_bytes_mean": statistics.fmean(high_precision_peaks),
        "high_precision_decision_count": float(cast(int, high_precision_decision_count)),
        "matched_decision_count": float(metadata_decision_count),
        "metadata_tensor_count": metadata_tensor_count,
        "tensor_names_access_count": float(cast(int, tensor_names_access_count)),
        "tensor_names_access_elapsed_ms_mean": statistics.fmean(tensor_names_access_ms),
        "tensor_names_access_peak_bytes_mean": statistics.fmean(tensor_names_access_peaks),
        "header_tensor_count": float(len(header_metadata.tensor_names)),
        "cross_shard_pair_count": cross_shard_pair_count,
        "cross_shard_fixup_count": float(cast(int, cross_shard_fixup_count)),
        "cross_shard_fixup_elapsed_ms_mean": statistics.fmean(cross_shard_fixup_ms),
        "cross_shard_fixup_peak_bytes_mean": statistics.fmean(cross_shard_fixup_peaks),
        "pair_count": float(pair_count),
        "shard_count": float(shard_count),
        "sample_count": float(samples),
        "decision_iterations": float(decision_iterations),
    }


def main() -> int:
    print(json.dumps(run_probe(), sort_keys=True))
    return 0


def _is_cross_shard_quantized_pair(metadata: QuantizedTensorMetadata, prefix: str) -> bool:
    shards = metadata.quantized_tensor_shards(prefix)
    return shards.get("weight") != shards.get("scales")


if __name__ == "__main__":
    raise SystemExit(main())
