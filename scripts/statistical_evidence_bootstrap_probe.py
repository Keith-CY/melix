from __future__ import annotations

import builtins
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

from worker.productization.statistical_evidence import build_paired_statistical_evidence


def _build_outcomes(sample_size: int) -> tuple[float, ...]:
    return tuple(
        1.0 if index % 7 in (0, 2, 3) else -1.0 if index % 11 == 0 else 0.0
        for index in range(sample_size)
    )


def run_probe() -> dict[str, float]:
    sample_size = int(os.environ.get("MELIX_STAT_EVIDENCE_SAMPLE_SIZE", "320"))
    bootstrap_iterations = int(os.environ.get("MELIX_STAT_EVIDENCE_BOOTSTRAP_ITERATIONS", "1200"))
    sample_count = int(os.environ.get("MELIX_STAT_EVIDENCE_PROBE_SAMPLES", "5"))
    outcomes = _build_outcomes(sample_size)
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    lower_bounds: list[float] = []
    upper_bounds: list[float] = []
    sorted_call_samples: list[float] = []

    for sample_index in range(sample_count):
        sorted_calls = 0
        original_sorted = builtins.sorted

        def tracked_sorted(values):
            nonlocal sorted_calls
            sorted_calls += 1
            return original_sorted(values)

        builtins.sorted = tracked_sorted
        try:
            tracemalloc.start()
            started = time.perf_counter()
            evidence = build_paired_statistical_evidence(
                paired_outcomes=outcomes,
                confidence_level=0.95,
                bootstrap_iterations=bootstrap_iterations,
                bootstrap_seed=1729 + sample_index,
            )
            elapsed_samples.append((time.perf_counter() - started) * 1000.0)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        finally:
            builtins.sorted = original_sorted
        peak_samples.append(float(peak))
        sorted_call_samples.append(float(sorted_calls))
        bootstrap = evidence["bootstrap"]
        lower_bounds.append(float(bootstrap["lower_bound"]))
        upper_bounds.append(float(bootstrap["upper_bound"]))

    if any(lower > upper for lower, upper in zip(lower_bounds, upper_bounds, strict=True)):
        raise SystemExit("bootstrap interval lower bound exceeded upper bound")

    return {
        "elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "peak_bytes_mean": statistics.fmean(peak_samples) if peak_samples else 0.0,
        "sample_count": float(sample_count),
        "sample_size": float(sample_size),
        "bootstrap_iterations": float(bootstrap_iterations),
        "sorted_calls_mean": statistics.fmean(sorted_call_samples),
        "lower_bound_mean": statistics.fmean(lower_bounds),
        "upper_bound_mean": statistics.fmean(upper_bounds),
    }


def main() -> int:
    metrics = run_probe()
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
