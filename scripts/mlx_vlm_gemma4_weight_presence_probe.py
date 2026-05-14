from __future__ import annotations

import json
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.runtime.mlx_vlm_runtime import _gemma4_multimodal_weight_presence

WEIGHT_NAME_COUNT = 50000
ITERATION_COUNT = 40
SAMPLE_COUNT = 5


def build_weights() -> dict[str, object]:
    names = [f"language_model.model.layers.{index}.self_attn.q_proj.weight" for index in range(WEIGHT_NAME_COUNT)]
    names[-3] = "vision_tower.encoder.layers.0.self_attn.q_proj.weight"
    names[-2] = "audio_tower.encoder.layers.0.self_attn.q_proj.weight"
    names[-1] = "language_model.model.layers.tail.mlp.down_proj.weight"
    sentinel = object()
    return {name: sentinel for name in names}


def measure_scan(weights: dict[str, object]) -> None:
    for _ in range(ITERATION_COUNT):
        has_vision, has_audio = _gemma4_multimodal_weight_presence(weights.keys())
        if not has_vision or not has_audio:
            raise RuntimeError("expected multimodal weight names")


def run_probe() -> dict[str, float]:
    weights = build_weights()
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    visited_samples: list[float] = []
    checksum = 0
    for _ in range(SAMPLE_COUNT):
        tracemalloc.start()
        started = time.perf_counter()
        measure_scan(weights)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        elapsed_samples.append(elapsed_ms)
        peak_samples.append(float(peak_bytes))
        visited_samples.append(float((WEIGHT_NAME_COUNT - 1) * ITERATION_COUNT))
        checksum += ITERATION_COUNT * 2
    return {
        "checksum": float(checksum),
        "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
        "has_audio": 1.0,
        "has_vision": 1.0,
        "iteration_count": float(ITERATION_COUNT),
        "peak_bytes_mean": round(statistics.fmean(peak_samples), 6),
        "sample_count": float(SAMPLE_COUNT),
        "visited_names_mean": round(statistics.fmean(visited_samples), 6),
        "weight_name_count": float(len(weights)),
    }


def main() -> int:
    print(json.dumps(run_probe(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
