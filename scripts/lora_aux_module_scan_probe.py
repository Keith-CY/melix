#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.model_ops import lora_runtime_metadata  # noqa: E402


def _prepare_model_dir(root: Path, filler_count: int) -> Path:
    model_dir = root / "base-model"
    model_dir.mkdir()
    for index in range(filler_count):
        (model_dir / f"filler_{index:05d}.txt").write_text("x", encoding="utf-8")
    (model_dir / "modeling_qwen2.py").write_text("# custom module\n", encoding="utf-8")
    return model_dir


def _measure(iterations: int, sample_count: int, filler_count: int) -> dict[str, float]:
    elapsed_samples: list[float] = []
    hit_samples: list[float] = []
    with tempfile.TemporaryDirectory() as tmp:
        model_dir = _prepare_model_dir(Path(tmp), filler_count)
        for _ in range(sample_count):
            hits = 0
            started = time.perf_counter()
            for _index in range(iterations):
                if lora_runtime_metadata._aux_modules_restored(model_dir):
                    hits += 1
            elapsed_samples.append((time.perf_counter() - started) * 1000.0)
            hit_samples.append(float(hits))

    return {
        "elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "filler_file_count": float(filler_count),
        "hit_count_mean": statistics.fmean(hit_samples),
        "iterations": float(iterations),
        "sample_count": float(sample_count),
    }


def main() -> int:
    iterations = int(os.environ.get("MELIX_LORA_AUX_MODULE_SCAN_ITERATIONS", "5000"))
    sample_count = int(os.environ.get("MELIX_LORA_AUX_MODULE_SCAN_SAMPLES", "5"))
    filler_count = int(os.environ.get("MELIX_LORA_AUX_MODULE_SCAN_FILLER_FILES", "2000"))
    print(json.dumps(_measure(iterations, sample_count, filler_count), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
