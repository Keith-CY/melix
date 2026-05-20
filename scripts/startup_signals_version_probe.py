from __future__ import annotations

import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path(os.environ.get("MELIX_STARTUP_SIGNALS_VERSION_REPO_ROOT", Path.cwd())).resolve()
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.productization import startup_signals  # noqa: E402


def _measure_update_result_allocations(iterations: int, sample_count: int) -> dict[str, float]:
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    available_count = 0

    for _ in range(sample_count):
        tracemalloc.start()
        started = time.perf_counter()
        available_count = 0
        for index in range(iterations):
            result = startup_signals.UpdateCheckResult(
                checked=True,
                update_available=(index % 2) == 0,
                installed_version="0.1.0",
                latest_version="0.2.0",
                channel="stable",
                summary="Update available: 0.2.0",
                detail="Current 0.1.0 on stable",
            )
            available_count += int(result.update_available)
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_samples.append(float(peak))

    return {
        "update_result_available_count": float(available_count),
        "update_result_elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "update_result_iterations": float(iterations),
        "update_result_peak_bytes_mean": statistics.fmean(peak_samples),
    }


def _version_pairs(count: int) -> list[tuple[str, str]]:
    versions = [
        f"v{major}.{minor}.{patch}{suffix}+build.{index}"
        for index in range(count)
        for major in range(1, 4)
        for minor in range(0, 4)
        for patch in range(0, 3)
        for suffix in ("", "-alpha", "-beta", "-rc1")
    ]
    differing_pairs = list(zip(versions, reversed(versions)))[: count // 3]
    exact_pairs = [(version, version) for version in versions[: count // 3]]
    prefix_equivalent_pairs = [
        (version, version[1:]) if index % 2 == 0 else (version[1:], version)
        for index, version in enumerate(versions[: count - len(differing_pairs) - len(exact_pairs)])
    ]
    return differing_pairs + exact_pairs + prefix_equivalent_pairs


def main() -> int:
    pair_count = 12_000
    sample_count = 7
    update_result_iterations = 25_000
    pairs = _version_pairs(pair_count)
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    comparison_total = 0

    for _ in range(sample_count):
        tracemalloc.start()
        started = time.perf_counter()
        comparison_total = 0
        for left, right in pairs:
            comparison_total += startup_signals.compare_versions(left, right)
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_samples.append(float(peak))

    metrics = {
        "comparison_total": float(comparison_total),
        "elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "pair_count": float(len(pairs)),
        "peak_bytes_mean": statistics.fmean(peak_samples),
        "sample_count": float(sample_count),
    }
    metrics.update(_measure_update_result_allocations(update_result_iterations, sample_count))
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    main()
