from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.runtime.runtime_utils import estimate_model_weight_resident_bytes


def _build_bundle(root: Path, file_count: int) -> tuple[Path, int]:
    bundle = root / "flat-model"
    bundle.mkdir()
    expected = 0
    for index in range(file_count):
        suffix = ".safetensors" if index % 2 == 0 else ".txt"
        payload = b"w" * ((index % 17) + 1)
        path = bundle / f"artifact-{index:05d}{suffix}"
        path.write_bytes(payload)
        if suffix == ".safetensors":
            expected += len(payload)
    return bundle, expected


def _build_indexed_bundle(root: Path, shard_count: int) -> tuple[Path, int]:
    bundle = root / "indexed-model"
    bundle.mkdir()
    expected = 0
    weight_map: dict[str, str] = {}
    for index in range(shard_count):
        payload = b"w" * ((index % 17) + 1)
        shard_name = f"model-{index:05d}.safetensors"
        (bundle / shard_name).write_bytes(payload)
        weight_map[f"layers.{index}.weight"] = shard_name
        expected += len(payload)
    for index in range(0, shard_count, 8):
        weight_map[f"layers.duplicate.{index}.weight"] = f"model-{index:05d}.safetensors"
    (bundle / "model.safetensors.index.json").write_text(
        json.dumps({"weight_map": weight_map}),
        encoding="utf-8",
    )
    return bundle, expected


def _sample(bundle: Path, expected: int, iterations: int) -> tuple[float, int, int]:
    started = time.perf_counter()
    checksum = 0
    for _ in range(iterations):
        observed = estimate_model_weight_resident_bytes(str(bundle))
        if observed != expected:
            raise RuntimeError(f"unexpected resident byte estimate: {observed} != {expected}")
        checksum += observed
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return elapsed_ms, checksum, expected


def main() -> int:
    file_count = int(os.environ.get("MELIX_RUNTIME_UTILS_WEIGHT_FILES", "3000"))
    shard_count = int(os.environ.get("MELIX_RUNTIME_UTILS_INDEXED_SHARDS", "1200"))
    iterations = int(os.environ.get("MELIX_RUNTIME_UTILS_WEIGHT_ITERATIONS", "8"))
    sample_count = int(os.environ.get("MELIX_RUNTIME_UTILS_WEIGHT_SAMPLES", "5"))
    elapsed: list[float] = []
    peaks: list[float] = []
    indexed_elapsed: list[float] = []
    indexed_peaks: list[float] = []
    checksum = 0
    expected = 0
    indexed_checksum = 0
    indexed_expected = 0
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        bundle, expected = _build_bundle(root, file_count)
        indexed_bundle, indexed_expected = _build_indexed_bundle(root, shard_count)
        for _ in range(sample_count):
            tracemalloc.start()
            elapsed_ms, checksum, expected = _sample(bundle, expected, iterations)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            elapsed.append(elapsed_ms)
            peaks.append(float(peak))

            tracemalloc.start()
            indexed_elapsed_ms, indexed_checksum, indexed_expected = _sample(
                indexed_bundle,
                indexed_expected,
                iterations,
            )
            _, indexed_peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            indexed_elapsed.append(indexed_elapsed_ms)
            indexed_peaks.append(float(indexed_peak))
    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(elapsed),
                "peak_bytes_mean": statistics.fmean(peaks),
                "indexed_elapsed_ms_mean": statistics.fmean(indexed_elapsed),
                "indexed_peak_bytes_mean": statistics.fmean(indexed_peaks),
                "file_count": float(file_count),
                "indexed_shard_count": float(shard_count),
                "iterations": float(iterations),
                "expected_bytes": float(expected),
                "indexed_expected_bytes": float(indexed_expected),
                "checksum": float(checksum),
                "indexed_checksum": float(indexed_checksum),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
