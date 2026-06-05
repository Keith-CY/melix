from __future__ import annotations

import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.engine.maintenance_core import _split_capability_values


def _baseline_split(raw_value: str) -> list[str]:
    return [
        part.strip()
        for part in raw_value.split(",")
        if part.strip()
    ]


def _payload(segment_count: int) -> str:
    values = (" text ", " image", "", " qwen ", " tool\t", "\n")
    return ",".join(values[index % len(values)] for index in range(segment_count))


def _run_split(splitter, raw_value: str, iterations: int) -> tuple[float, int, int]:
    checksum = 0
    segment_count = 0
    started = time.perf_counter()
    for _ in range(iterations):
        values = splitter(raw_value)
        if values[:5] != ["text", "image", "qwen", "tool", "text"]:
            raise SystemExit(f"unexpected split prefix: {values[:5]!r}")
        checksum += sum(len(value) for value in values)
        segment_count += len(values)
    return (time.perf_counter() - started) * 1000.0, checksum, segment_count


def _run_empty_split(splitter, iterations: int) -> tuple[float, int]:
    checksum = 0
    started = time.perf_counter()
    for _ in range(iterations):
        empty_values = splitter("")
        whitespace_values = splitter(" \t\n ")
        singleton_values = splitter(" text ")
        if empty_values or whitespace_values or singleton_values != ["text"]:
            raise SystemExit(
                "unexpected empty/singleton split output: "
                f"{empty_values!r}, {whitespace_values!r}, {singleton_values!r}"
            )
        checksum += len(singleton_values)
    return (time.perf_counter() - started) * 1000.0, checksum


def main() -> int:
    iterations = int(os.environ.get("MELIX_MAINTENANCE_CAPABILITY_SPLIT_ITERATIONS", "50000"))
    sample_count = int(os.environ.get("MELIX_MAINTENANCE_CAPABILITY_SPLIT_SAMPLES", "5"))
    value_segments = int(os.environ.get("MELIX_MAINTENANCE_CAPABILITY_SPLIT_SEGMENTS", "72"))
    raw_value = _payload(value_segments)

    expected = _baseline_split(raw_value)
    observed = _split_capability_values(raw_value)
    if observed != expected:
        raise SystemExit(f"split output drifted: {observed!r} != {expected!r}")

    baseline_elapsed: list[float] = []
    optimized_elapsed: list[float] = []
    empty_baseline_elapsed: list[float] = []
    empty_optimized_elapsed: list[float] = []
    peak_bytes: list[float] = []
    checksum = 0
    empty_checksum = 0
    segment_total = 0
    for _ in range(sample_count):
        elapsed_ms, checksum, segment_total = _run_split(
            _baseline_split,
            raw_value,
            iterations,
        )
        baseline_elapsed.append(elapsed_ms)

        elapsed_ms, empty_checksum = _run_empty_split(
            _baseline_split,
            iterations,
        )
        empty_baseline_elapsed.append(elapsed_ms)

        elapsed_ms, checksum, segment_total = _run_split(
            _split_capability_values,
            raw_value,
            iterations,
        )
        optimized_elapsed.append(elapsed_ms)

        elapsed_ms, empty_checksum = _run_empty_split(
            _split_capability_values,
            iterations,
        )
        empty_optimized_elapsed.append(elapsed_ms)

        tracemalloc.start()
        _run_split(
            _split_capability_values,
            raw_value,
            1,
        )
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_bytes.append(float(peak))

    baseline_mean = statistics.fmean(baseline_elapsed)
    optimized_mean = statistics.fmean(optimized_elapsed)
    empty_baseline_mean = statistics.fmean(empty_baseline_elapsed)
    empty_optimized_mean = statistics.fmean(empty_optimized_elapsed)
    metrics = {
        "baseline_elapsed_ms_mean": baseline_mean,
        "optimized_elapsed_ms_mean": optimized_mean,
        "elapsed_ms_mean": optimized_mean,
        "delta_ms_mean": optimized_mean - baseline_mean,
        "empty_baseline_elapsed_ms_mean": empty_baseline_mean,
        "empty_optimized_elapsed_ms_mean": empty_optimized_mean,
        "empty_delta_ms_mean": empty_optimized_mean - empty_baseline_mean,
        "empty_speedup": empty_baseline_mean / empty_optimized_mean if empty_optimized_mean > 0 else 0.0,
        "speedup": baseline_mean / optimized_mean if optimized_mean > 0 else 0.0,
        "peak_bytes_mean": statistics.fmean(peak_bytes),
        "segment_count": float(value_segments),
        "iteration_count": float(iterations),
        "sample_count": float(sample_count),
        "split_values_per_sample": float(segment_total),
        "checksum": float(checksum),
        "empty_checksum": float(empty_checksum),
    }
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
