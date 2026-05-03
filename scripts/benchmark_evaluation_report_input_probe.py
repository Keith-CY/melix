#!/usr/bin/env python3
from __future__ import annotations

import gc
import json
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.productization.benchmark_evaluation_report import (  # noqa: E402
    build_benchmark_evaluation_report,
    load_report_input,
)
from worker.productization.pr_scoped_performance import _build_large_benchmark_bundle  # noqa: E402

SAMPLE_COUNT = 5


def main() -> int:
    baseline = _build_large_benchmark_bundle(base_value=100.0)
    candidate = _build_large_benchmark_bundle(base_value=108.0)
    load_samples: list[float] = []
    report_samples: list[float] = []
    peak_samples: list[float] = []
    row_count = 0.0

    with tempfile.TemporaryDirectory(prefix="melix-benchmark-report-input-") as temp_dir:
        input_path = Path(temp_dir) / "benchmark-evaluation-export.json"
        input_path.write_text(json.dumps(baseline) + "\n", encoding="utf-8")
        for _ in range(SAMPLE_COUNT):
            gc.collect()
            load_started = time.perf_counter()
            loaded_baseline = load_report_input(input_path)
            load_samples.append((time.perf_counter() - load_started) * 1000.0)

            tracemalloc.start()
            report_started = time.perf_counter()
            report = build_benchmark_evaluation_report(
                baseline=loaded_baseline,
                candidate=candidate,
            )
            report_samples.append((time.perf_counter() - report_started) * 1000.0)
            _, peak_bytes = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peak_samples.append(float(peak_bytes))
            row_count = float(len(report.get("rows", [])))

    print(
        json.dumps(
            {
                "load_input_ms_mean": round(statistics.fmean(load_samples), 6),
                "elapsed_ms_mean": round(statistics.fmean(report_samples), 6),
                "peak_bytes_mean": round(statistics.fmean(peak_samples), 3),
                "row_count": row_count,
                "sample_count": float(SAMPLE_COUNT),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
