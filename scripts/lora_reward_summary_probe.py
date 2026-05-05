from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "services/mlx-worker-python"))

from worker.model_ops import lora_training_pipeline as lora_training_pipeline_module


def _build_samples(sample_count: int, candidate_count: int) -> list[dict[str, object]]:
    samples: list[dict[str, object]] = []
    for sample_index in range(sample_count):
        base = (sample_index % 17) / 17.0
        candidates = [
            {"score": ((sample_index * 31 + candidate_index * 7) % 101) / 100.0 - base}
            for candidate_index in range(candidate_count)
        ]
        samples.append(
            {
                "reward_score": base,
                "candidates": candidates,
            }
        )
    return samples


def main() -> int:
    sample_count = 5000
    candidate_count = 32
    iteration_count = 8
    samples = _build_samples(sample_count, candidate_count)
    original_sorted = sorted
    elapsed_ms: list[float] = []
    sorted_calls: list[int] = []
    checksum = 0.0

    def counting_sorted(values):  # type: ignore[no-untyped-def]
        sorted_calls[-1] += 1
        return original_sorted(values)

    previous_sorted = getattr(lora_training_pipeline_module, "sorted", None)
    had_module_sorted = hasattr(lora_training_pipeline_module, "sorted")
    setattr(lora_training_pipeline_module, "sorted", counting_sorted)
    try:
        for _ in range(iteration_count):
            sorted_calls.append(0)
            start = time.perf_counter()
            summary = lora_training_pipeline_module._reward_summary(samples)
            elapsed_ms.append((time.perf_counter() - start) * 1000.0)
            checksum += float(summary["candidate_group_reward_margin_mean"])
    finally:
        if had_module_sorted:
            setattr(lora_training_pipeline_module, "sorted", previous_sorted)
        else:
            delattr(lora_training_pipeline_module, "sorted")

    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.mean(elapsed_ms),
                "sorted_calls_mean": statistics.mean(sorted_calls),
                "sample_count": float(sample_count),
                "candidate_count": float(candidate_count),
                "checksum": checksum,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
