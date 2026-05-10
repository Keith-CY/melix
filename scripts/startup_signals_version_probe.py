from __future__ import annotations

import json
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.productization import startup_signals  # noqa: E402


def _version_pairs(count: int) -> list[tuple[str, str]]:
    versions = [
        f"v{major}.{minor}.{patch}{suffix}+build.{index}"
        for index in range(count)
        for major in range(1, 4)
        for minor in range(0, 4)
        for patch in range(0, 3)
        for suffix in ("", "-alpha", "-beta", "-rc1")
    ]
    return list(zip(versions, reversed(versions)))[:count]


def main() -> int:
    pair_count = 12_000
    sample_count = 7
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

    print(
        json.dumps(
            {
                "comparison_total": float(comparison_total),
                "elapsed_ms_mean": statistics.fmean(elapsed_samples),
                "pair_count": float(len(pairs)),
                "peak_bytes_mean": statistics.fmean(peak_samples),
                "sample_count": float(sample_count),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    main()
