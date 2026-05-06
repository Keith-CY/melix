#!/usr/bin/env python3
"""Measure category-breakdown aggregation for statistical evidence."""

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

from worker.productization.statistical_evidence import build_category_breakdown


def _build_rows(row_count: int, category_count: int) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "category_label": f"category-{index % category_count:03d}",
            "base_correct": index % 5 in (0, 1),
            "target_correct": index % 7 in (0, 1, 2, 3),
        }
        for index in range(row_count)
    )


def main() -> int:
    row_count = int(os.environ.get("MELIX_STAT_CATEGORY_ROWS", "50000"))
    category_count = int(os.environ.get("MELIX_STAT_CATEGORY_COUNT", "64"))
    sample_count = int(os.environ.get("MELIX_STAT_CATEGORY_PROBE_SAMPLES", "5"))
    rows = _build_rows(row_count=row_count, category_count=category_count)

    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    checksum = 0.0
    for _ in range(sample_count):
        started = time.perf_counter()
        breakdown = build_category_breakdown(rows=rows)
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        checksum += sum(
            float(payload["sample_size"])
            + float(payload["base_accuracy"])
            + float(payload["target_accuracy"])
            + float(payload["delta_accuracy"])
            for payload in breakdown.values()
        )
        if len(breakdown) != category_count:
            raise SystemExit(
                f"unexpected category count: {len(breakdown)} != {category_count}"
            )
        if sum(int(payload["sample_size"]) for payload in breakdown.values()) != row_count:
            raise SystemExit("category breakdown dropped rows")

        tracemalloc.start()
        memory_breakdown = build_category_breakdown(rows=rows)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_samples.append(float(peak))
        if memory_breakdown != breakdown:
            raise SystemExit("category breakdown changed between timing and memory passes")

    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(elapsed_samples),
                "peak_bytes_mean": statistics.fmean(peak_samples),
                "row_count": float(row_count),
                "category_count": float(category_count),
                "sample_count": float(sample_count),
                "checksum": checksum,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
