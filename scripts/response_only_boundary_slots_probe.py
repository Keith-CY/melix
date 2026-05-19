#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path(os.environ.get("MELIX_PROBE_REPO_ROOT", Path.cwd())).resolve()
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.model_ops.response_only_boundary import (  # noqa: E402
    ResponseOnlyBoundary,
    aggregate_response_only_boundaries,
)


def _build_boundaries(count: int) -> tuple[ResponseOnlyBoundary, ...]:
    return tuple(
        ResponseOnlyBoundary(
            assistant_offset=16 + (index % 257),
            total_tokens=16 + (index % 257) + 8 + (index % 97),
        )
        for index in range(count)
    )


def _measure(boundary_count: int, sample_count: int) -> dict[str, float]:
    construction_elapsed_samples: list[float] = []
    aggregation_elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    instance_dict_samples: list[float] = []
    checksum = 0

    for _ in range(sample_count):
        tracemalloc.start()
        construction_started = time.perf_counter()
        boundaries = _build_boundaries(boundary_count)
        construction_elapsed_samples.append((time.perf_counter() - construction_started) * 1000.0)
        _, construction_peak = tracemalloc.get_traced_memory()

        instance_dict_samples.append(
            float(sum(1 for boundary in boundaries if hasattr(boundary, "__dict__")))
        )

        aggregation_started = time.perf_counter()
        aggregate = aggregate_response_only_boundaries(boundaries, max_seq_length=192)
        aggregation_elapsed_samples.append((time.perf_counter() - aggregation_started) * 1000.0)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_samples.append(float(max(peak, construction_peak)))
        checksum += (
            aggregate.sample_count
            + aggregate.boundary_min
            + aggregate.boundary_max
            + aggregate.trainable_response_token_count
        )

    return {
        "construction_elapsed_ms_mean": statistics.fmean(construction_elapsed_samples),
        "aggregation_elapsed_ms_mean": statistics.fmean(aggregation_elapsed_samples),
        "peak_bytes_mean": statistics.fmean(peak_samples),
        "instance_dict_count_mean": statistics.fmean(instance_dict_samples),
        "boundary_count": float(boundary_count),
        "sample_count": float(sample_count),
        "checksum": float(checksum),
    }


def main() -> int:
    boundary_count = int(os.environ.get("MELIX_RESPONSE_BOUNDARY_SLOT_PROBE_COUNT", "50000"))
    sample_count = int(os.environ.get("MELIX_RESPONSE_BOUNDARY_SLOT_PROBE_SAMPLES", "5"))
    print(json.dumps(_measure(boundary_count, sample_count), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
