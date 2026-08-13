from __future__ import annotations

import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.engine.maintenance_core import BenchSample, MaintenanceCore

SAMPLE_COUNT = int(os.environ.get("MELIX_MAINTENANCE_CATEGORICAL_PROBE_SAMPLES", "5"))
ITERATION_COUNT = int(os.environ.get("MELIX_MAINTENANCE_CATEGORICAL_PROBE_ITERATIONS", "400"))
UNIFORM_COUNT = int(os.environ.get("MELIX_MAINTENANCE_CATEGORICAL_PROBE_VALUES", "20000"))
MIXED_COUNT = UNIFORM_COUNT

MAPPING = {
    "": 0.0,
    "baseline": 0.0,
    "single_stream": 1.0,
    "image_cache_reuse": 2.0,
    "mixed": 5.0,
}


def _legacy_categorical_metric_code_for_samples(
    samples: list[Any],
    field_name: str,
    mapping: dict[str, float],
) -> float:
    values = [str(getattr(sample, field_name, "") or "") for sample in samples]
    distinct_values = set(values)
    if len(distinct_values) > 1:
        return MaintenanceCore._categorical_metric_code("mixed", mapping)
    return MaintenanceCore._categorical_metric_code(next(iter(distinct_values)), mapping)


def _samples(count: int, *, mixed: bool) -> list[BenchSample]:
    samples: list[BenchSample] = []
    for index in range(count):
        mode = "image_cache_reuse" if mixed and index >= 1 else "single_stream"
        samples.append(
            BenchSample(
                ttft_ms=10.0,
                total_latency_ms=20.0,
                completion_tokens=2,
                multimodal_decode_mode=mode,
            )
        )
    return samples


def _time_case(samples: list[BenchSample], *, legacy: bool) -> tuple[float, float]:
    helper = (
        _legacy_categorical_metric_code_for_samples
        if legacy
        else MaintenanceCore._categorical_metric_code_for_samples
    )
    checksum = 0.0
    started = time.perf_counter()
    for _ in range(ITERATION_COUNT):
        checksum += helper(samples, "multimodal_decode_mode", MAPPING)
    return (time.perf_counter() - started) * 1000.0, checksum


def main() -> int:
    uniform_samples = _samples(UNIFORM_COUNT, mixed=False)
    mixed_samples = _samples(MIXED_COUNT, mixed=True)
    uniform_legacy: list[float] = []
    uniform_current: list[float] = []
    mixed_legacy: list[float] = []
    mixed_current: list[float] = []
    peak_samples: list[float] = []
    checksum = 0.0

    for _ in range(SAMPLE_COUNT):
        tracemalloc.start()
        elapsed, partial = _time_case(uniform_samples, legacy=True)
        uniform_legacy.append(elapsed)
        checksum += partial
        elapsed, partial = _time_case(uniform_samples, legacy=False)
        uniform_current.append(elapsed)
        checksum += partial
        elapsed, partial = _time_case(mixed_samples, legacy=True)
        mixed_legacy.append(elapsed)
        checksum += partial
        elapsed, partial = _time_case(mixed_samples, legacy=False)
        mixed_current.append(elapsed)
        checksum += partial
        _, peak = tracemalloc.get_traced_memory()
        peak_samples.append(float(peak))
        tracemalloc.stop()

    uniform_old = statistics.fmean(uniform_legacy)
    uniform_new = statistics.fmean(uniform_current)
    mixed_old = statistics.fmean(mixed_legacy)
    mixed_new = statistics.fmean(mixed_current)

    print(
        json.dumps(
            {
                "checksum": float(checksum),
                "iteration_count": float(ITERATION_COUNT),
                "mixed_current_ms_mean": round(mixed_new, 6),
                "mixed_delta_ms_mean": round(mixed_new - mixed_old, 6),
                "mixed_legacy_ms_mean": round(mixed_old, 6),
                "mixed_speedup": round(mixed_old / mixed_new, 6) if mixed_new else 0.0,
                "peak_bytes_mean": round(statistics.fmean(peak_samples), 3),
                "sample_count": float(SAMPLE_COUNT),
                "uniform_current_ms_mean": round(uniform_new, 6),
                "uniform_delta_ms_mean": round(uniform_new - uniform_old, 6),
                "uniform_legacy_ms_mean": round(uniform_old, 6),
                "uniform_speedup": round(uniform_old / uniform_new, 6) if uniform_new else 0.0,
                "value_count": float(UNIFORM_COUNT),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
