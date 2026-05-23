from __future__ import annotations

import json
import statistics
import sys
import time
import tracemalloc
from collections.abc import Iterable
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.runtime.mlx_vlm_runtime import MLXVLMRuntime, _gemma4_multimodal_weight_presence

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


def measure_once(weight_names: Iterable[str]) -> tuple[float, int, int, bool, bool]:
    visited = 0
    checksum = 0
    has_vision = False
    has_audio = False
    started = time.perf_counter()
    for _ in range(ITERATION_COUNT):
        has_vision, has_audio = _gemma4_multimodal_weight_presence(weight_names)
        if not has_vision or not has_audio:
            raise RuntimeError("expected multimodal weight names")
        visited += WEIGHT_NAME_COUNT - 1
        checksum += int(has_vision) + int(has_audio)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return elapsed_ms, visited, checksum, has_vision, has_audio


def warm_up(weight_names: Iterable[str]) -> None:
    measure_once(weight_names)


def run_probe() -> dict[str, float]:
    weights = build_weights()
    weight_names = weights.keys()
    tracemalloc.start()
    warm_up(weight_names)
    tracemalloc.stop()
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    visited_samples: list[float] = []
    checksum = 0
    has_vision = False
    has_audio = False
    for _ in range(SAMPLE_COUNT):
        tracemalloc.start()
        elapsed_ms, visited, sample_checksum, has_vision, has_audio = measure_once(weight_names)
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        elapsed_samples.append(elapsed_ms)
        peak_samples.append(float(peak_bytes))
        visited_samples.append(float(visited))
        checksum += sample_checksum
    runtime = MLXVLMRuntime()
    loaded_model = {
        "model": SimpleNamespace(),
        "processor": SimpleNamespace(eos_token_id=1),
    }
    scheduler = runtime._text_only_batch_generator_scheduler(loaded_model)
    scheduler._stats.prefill_response_count = 2
    scheduler._stats.prefill_step_count = 2
    probe = runtime.last_probe_snapshot()
    runtime.close_loaded_model(loaded_model)
    if runtime._loaded_models_with_schedulers:
        raise SystemExit("scheduler model tracking was not cleared")

    return {
        "checksum": float(checksum),
        "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
        "has_audio": float(has_audio),
        "has_vision": float(has_vision),
        "iteration_count": float(ITERATION_COUNT),
        "live_prefill_response_count": float(probe.text_batch_generator_prefill_response_count),
        "live_prefill_step_count": float(probe.text_batch_generator_prefill_step_count),
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
