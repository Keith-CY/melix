#!/usr/bin/env python3
"""Measure event-extraction semantic action value-group reuse."""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.productization import event_extraction as event_extraction_module  # noqa: E402


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return max(1, int(value))


def _run_probe(*, counts: Iterable[int], iterations: int, samples: int) -> dict[str, float]:
    original_combinations = event_extraction_module.combinations
    elapsed_ms: list[float] = []
    peak_bytes: list[float] = []
    combination_calls: list[float] = []
    group_count = 0
    checksum = 0

    def counted_combinations(*args: object, **kwargs: object) -> object:
        nonlocal current_combination_calls
        current_combination_calls += 1
        return original_combinations(*args, **kwargs)

    event_extraction_module.combinations = counted_combinations
    try:
        for _sample_index in range(samples):
            current_combination_calls = 0
            cache_clear = getattr(event_extraction_module._semantic_value_groups, "cache_clear", None)
            if cache_clear is not None:
                cache_clear()
            tracemalloc.start()
            started = time.perf_counter()
            sample_group_count = 0
            sample_checksum = 0
            for _ in range(iterations):
                for value_count in counts:
                    groups = event_extraction_module._semantic_value_groups(value_count)
                    sample_group_count += len(groups)
                    sample_checksum += sum(sum(group) + len(group) * 17 for group in groups)
            elapsed_ms.append((time.perf_counter() - started) * 1000.0)
            _current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peak_bytes.append(float(peak))
            combination_calls.append(float(current_combination_calls))
            group_count = sample_group_count
            checksum += sample_checksum
    finally:
        event_extraction_module.combinations = original_combinations

    return {
        "elapsed_ms_mean": statistics.fmean(elapsed_ms),
        "elapsed_ms_min": min(elapsed_ms),
        "peak_bytes_mean": statistics.fmean(peak_bytes),
        "combination_build_calls_mean": statistics.fmean(combination_calls),
        "iterations_per_sample": float(iterations),
        "sample_count": float(samples),
        "value_count_max": float(max(counts)),
        "group_count_per_sample": float(group_count),
        "checksum": float(checksum),
    }


def main() -> int:
    counts = tuple(
        int(part)
        for part in os.getenv("MELIX_EVENT_SEMANTIC_GROUP_PROBE_COUNTS", "4,8,12,16").split(",")
        if part.strip()
    )
    metrics = _run_probe(
        counts=counts,
        iterations=_env_int("MELIX_EVENT_SEMANTIC_GROUP_PROBE_ITERATIONS", 20000),
        samples=_env_int("MELIX_EVENT_SEMANTIC_GROUP_PROBE_SAMPLES", 5),
    )
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
