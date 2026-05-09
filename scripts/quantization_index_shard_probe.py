from __future__ import annotations

import builtins
import json
import os
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Any

REPO_ROOT = Path(os.environ.get("MELIX_QUANTIZATION_INDEX_SHARD_REPO_ROOT", Path.cwd()))
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.model_ops.quantization_pipeline import _smoke_required_files_for_backend


def _write_probe_bundle(bundle_path: Path, *, entry_count: int) -> None:
    bundle_path.mkdir(parents=True, exist_ok=True)
    (bundle_path / "tokenizer.json").write_text("{}\n", encoding="utf-8")
    (bundle_path / "model-00001-of-01000.safetensors").write_bytes(b"probe-shard")
    weight_map: dict[str, object] = {}
    for index in range(entry_count):
        shard = f"model-{(entry_count - index) % 1000 + 1:05d}-of-01000.safetensors"
        weight_map[f"layers.{index}.weight"] = shard
    weight_map["layers.duplicate.weight"] = "model-00001-of-01000.safetensors"
    weight_map["layers.empty.weight"] = ""
    weight_map["layers.non_string.weight"] = entry_count
    (bundle_path / "model.safetensors.index.json").write_text(
        json.dumps({"weight_map": weight_map}),
        encoding="utf-8",
    )


def _measure_once(bundle_path: Path, *, iterations: int) -> dict[str, float]:
    real_sorted = builtins.sorted
    sorted_calls = 0

    def counting_sorted(*args: Any, **kwargs: Any) -> Any:
        nonlocal sorted_calls
        sorted_calls += 1
        return real_sorted(*args, **kwargs)

    builtins.sorted = counting_sorted
    tracemalloc.start()
    started = time.perf_counter()
    try:
        for _ in range(iterations):
            required = _smoke_required_files_for_backend(
                bundle_path,
                quantization_backend="mlx_lm_convert",
            )
            if required != (
                "config.json",
                "tokenizer.json",
                "model.safetensors.index.json",
                "model-00001-of-01000.safetensors",
            ):
                raise SystemExit(f"unexpected required file tuple: {required!r}")
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        _, peak = tracemalloc.get_traced_memory()
    finally:
        builtins.sorted = real_sorted
        if tracemalloc.is_tracing():
            tracemalloc.stop()
    return {
        "elapsed_ms": elapsed_ms,
        "peak_bytes": float(peak),
        "sorted_calls": float(sorted_calls),
    }


def main() -> int:
    entry_count = int(os.environ.get("MELIX_QUANTIZATION_INDEX_SHARD_PROBE_ENTRIES", "5000"))
    iterations = int(os.environ.get("MELIX_QUANTIZATION_INDEX_SHARD_PROBE_ITERATIONS", "8"))
    samples = int(os.environ.get("MELIX_QUANTIZATION_INDEX_SHARD_PROBE_SAMPLES", "5"))
    with tempfile.TemporaryDirectory(prefix="melix-quant-index-probe-") as temp_dir:
        bundle_path = Path(temp_dir) / "bundle"
        _write_probe_bundle(bundle_path, entry_count=entry_count)
        measurements = [_measure_once(bundle_path, iterations=iterations) for _ in range(samples)]
    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(item["elapsed_ms"] for item in measurements),
                "peak_bytes_mean": statistics.fmean(item["peak_bytes"] for item in measurements),
                "sorted_calls_mean": statistics.fmean(item["sorted_calls"] for item in measurements),
                "weight_map_entries": float(entry_count + 3),
                "iterations_per_sample": float(iterations),
                "sample_count": float(samples),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
