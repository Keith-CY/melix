from __future__ import annotations

import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.runtime.image_family_adapters import resolve_image_family_config


class CopyCountingMetadata(Mapping[str, str]):
    def __init__(self, payload: Mapping[str, str]) -> None:
        self._payload = dict(payload)
        self.iteration_count = 0

    def __iter__(self):
        self.iteration_count += 1
        return iter(self._payload)

    def __len__(self) -> int:
        return len(self._payload)

    def __getitem__(self, key: str) -> str:
        return self._payload[key]


def _payload(index: int) -> dict[str, str]:
    families = ("deterministic-v1", "kontext-v1", "fill-v1", "qwenimage-v1", "fibo-v1", "klein-v1")
    task_kind = "image-text-to-image" if index % 3 else "text-to-image"
    return {
        "melix.image.family_id": families[index % len(families)],
        "melix.image.backend_id": "deterministic",
        "melix.image.task_kind": task_kind,
        "melix.image.supports_generation": "true" if index % 5 else "false",
        "melix.image.supports_edit": "true" if index % 7 else "false",
        "melix.image.default_workflow_role": "edit" if task_kind == "image-text-to-image" else "generate",
    }


def _measure(iterations: int) -> dict[str, float]:
    metadata_samples = [CopyCountingMetadata(_payload(index)) for index in range(64)]
    checksum = 0
    tracemalloc.start()
    started = time.perf_counter()
    for index in range(iterations):
        metadata = metadata_samples[index % len(metadata_samples)]
        config = resolve_image_family_config(
            metadata,
            model_path=f"models/image-family-probe-{index % 11}",
            default_task_kind="text-to-image",
        )
        checksum += len(config.family_id) + int(config.supports_generation) + int(config.supports_edit)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    iteration_calls = sum(sample.iteration_count for sample in metadata_samples)
    return {
        "elapsed_ms": elapsed_ms,
        "peak_bytes": float(peak_bytes),
        "metadata_iteration_calls": float(iteration_calls),
        "checksum": float(checksum),
    }


def main() -> None:
    iterations = int(os.environ.get("MELIX_IMAGE_FAMILY_CONFIG_ITERATIONS", "80000"))
    sample_count = int(os.environ.get("MELIX_IMAGE_FAMILY_CONFIG_SAMPLES", "5"))
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    iteration_call_samples: list[float] = []
    checksum = 0.0

    for _ in range(sample_count):
        sample = _measure(iterations)
        elapsed_samples.append(sample["elapsed_ms"])
        peak_samples.append(sample["peak_bytes"])
        iteration_call_samples.append(sample["metadata_iteration_calls"])
        checksum = sample["checksum"]

    print(
        json.dumps(
            {
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "elapsed_ms_min": round(min(elapsed_samples), 6),
                "peak_bytes_mean": round(statistics.fmean(peak_samples), 3),
                "metadata_iteration_calls_mean": round(statistics.fmean(iteration_call_samples), 3),
                "iteration_count": float(iterations),
                "sample_count": float(sample_count),
                "checksum": checksum,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
