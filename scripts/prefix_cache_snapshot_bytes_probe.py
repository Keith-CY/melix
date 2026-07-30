#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import statistics
import sys
import time
import tracemalloc
from types import SimpleNamespace

from pathlib import Path

REPO_ROOT = Path(os.environ.get("MELIX_PREFIX_CACHE_SNAPSHOT_REPO_ROOT", Path.cwd()))
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.runtime.prefix_block_store import estimate_cache_snapshot_bytes  # noqa: E402


class FakeTensor:
    __slots__ = ("nbytes",)

    def __init__(self, nbytes: int) -> None:
        self.nbytes = nbytes


class FakeFallbackTensor:
    __slots__ = ("itemsize", "size")

    def __init__(self, size: int, itemsize: int) -> None:
        self.size = size
        self.itemsize = itemsize


def _build_cache(layer_count: int) -> tuple[list[SimpleNamespace], int]:
    cache: list[SimpleNamespace] = []
    expected = 0
    for index in range(layer_count):
        first = FakeTensor(128 + (index % 17))
        second = FakeFallbackTensor(16 + (index % 11), 4)
        if index % 3 == 0:
            state = [first, second]
            cache.append(SimpleNamespace(state=state))
        elif index % 3 == 1:
            cache.append(SimpleNamespace(keys=first, values=second))
        else:
            cache.append(SimpleNamespace(state=first))
        expected += first.nbytes + second.size * second.itemsize if index % 3 != 2 else first.nbytes
    return cache, expected


def measure(*, layer_count: int, iterations: int, samples: int) -> dict[str, float]:
    cache, expected = _build_cache(layer_count)
    elapsed_ms: list[float] = []
    peak_bytes: list[float] = []
    checksum = 0
    for _ in range(samples):
        tracemalloc.start()
        started = time.perf_counter()
        checksum = 0
        for _iteration in range(iterations):
            observed = estimate_cache_snapshot_bytes(cache)
            if observed != expected:
                raise RuntimeError(f"unexpected cache byte estimate: {observed} != {expected}")
            checksum += observed
        elapsed_ms.append((time.perf_counter() - started) * 1000.0)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_bytes.append(float(peak))
    return {
        "checksum": float(checksum),
        "elapsed_ms_mean": statistics.fmean(elapsed_ms),
        "elapsed_ms_min": min(elapsed_ms),
        "elapsed_ms_p95": sorted(elapsed_ms)[int((len(elapsed_ms) - 1) * 0.95)],
        "iteration_count": float(iterations),
        "layer_count": float(layer_count),
        "peak_bytes_mean": statistics.fmean(peak_bytes),
        "sample_count": float(samples),
    }


def main() -> int:
    layer_count = int(os.environ.get("MELIX_PREFIX_CACHE_SNAPSHOT_LAYERS", "4096"))
    iterations = int(os.environ.get("MELIX_PREFIX_CACHE_SNAPSHOT_ITERATIONS", "80"))
    samples = int(os.environ.get("MELIX_PREFIX_CACHE_SNAPSHOT_SAMPLES", "5"))
    print(json.dumps(measure(layer_count=layer_count, iterations=iterations, samples=samples), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
