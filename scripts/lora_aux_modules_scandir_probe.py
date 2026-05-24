#!/usr/bin/env python3
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

from worker.model_ops import lora_runtime_metadata as metadata_module  # noqa: E402


def _int_env(name: str, default: int) -> int:
    raw_value = os.environ.get(name, "")
    return int(raw_value) if raw_value else default


def _seed_base_model(root: Path, *, noise_count: int, aux_index: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for index in range(noise_count):
        (root / f"noise-{index:05d}.txt").write_text("noise\n", encoding="utf-8")
    (root / f"tokenization_custom_{aux_index:05d}.py").write_text(
        "# auxiliary tokenizer module\n", encoding="utf-8"
    )


def _measure(*, noise_count: int, sample_count: int) -> dict[str, float]:
    elapsed_ms: list[float] = []
    peak_bytes: list[float] = []
    scandir_calls: list[float] = []

    with tempfile.TemporaryDirectory(prefix="melix-lora-aux-probe-") as temp_dir:
        base_model_dir = Path(temp_dir) / "base-model"
        _seed_base_model(base_model_dir, noise_count=noise_count, aux_index=noise_count)

        original_scandir = metadata_module.os.scandir
        for _ in range(sample_count):
            call_count = 0

            def counting_scandir(path: str | Path):
                nonlocal call_count
                call_count += 1
                return original_scandir(path)

            metadata_module.os.scandir = counting_scandir
            tracemalloc.start()
            started = time.perf_counter()
            try:
                restored = metadata_module._aux_modules_restored(base_model_dir)
            finally:
                elapsed = (time.perf_counter() - started) * 1000.0
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                metadata_module.os.scandir = original_scandir
            if not restored:
                raise RuntimeError("expected auxiliary module detection to return true")
            elapsed_ms.append(elapsed)
            peak_bytes.append(float(peak))
            scandir_calls.append(float(call_count))

    return {
        "elapsed_ms_mean": statistics.fmean(elapsed_ms),
        "elapsed_ms_min": min(elapsed_ms),
        "peak_bytes_mean": statistics.fmean(peak_bytes),
        "scandir_calls_mean": statistics.fmean(scandir_calls),
        "noise_file_count": float(noise_count),
        "sample_count": float(sample_count),
    }


def main() -> int:
    noise_count = _int_env("MELIX_LORA_AUX_MODULES_PROBE_NOISE_FILES", 4000)
    sample_count = _int_env("MELIX_LORA_AUX_MODULES_PROBE_SAMPLES", 7)
    print(json.dumps(_measure(noise_count=noise_count, sample_count=sample_count), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
