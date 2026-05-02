#!/usr/bin/env python3
from __future__ import annotations

import json
import runpy
import statistics
import tempfile
import time
from pathlib import Path


def main() -> int:
    report_script = runpy.run_path(str(Path(__file__).resolve().parent / "pr_scoped_performance_report.py"))
    load_results = report_script["_load_results"]

    file_count = 2000
    sample_count = 5
    elapsed_samples: list[float] = []
    result_count = 0

    with tempfile.TemporaryDirectory(prefix="melix-pr-perf-report-results-") as temp_dir:
        results_dir = Path(temp_dir) / "results"
        results_dir.mkdir()
        for index in range(file_count):
            (results_dir / f"result-{index:05d}.json").write_text(
                json.dumps(
                    {
                        "base": {"elapsed_ms_mean": float(index)},
                        "head": {"elapsed_ms_mean": float(index) - 1.0},
                        "probe": {"id": f"probe-{index:05d}"},
                    }
                ),
                encoding="utf-8",
            )
        (results_dir / "ignored.txt").write_text("ignored", encoding="utf-8")

        for _ in range(sample_count):
            started = time.perf_counter()
            loaded = load_results(results_dir)
            elapsed_samples.append((time.perf_counter() - started) * 1000.0)
            result_count = len(loaded)

    print(
        json.dumps(
            {
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "elapsed_ms_min": round(min(elapsed_samples), 6),
                "file_count": float(file_count),
                "result_count": float(result_count),
                "sample_count": float(sample_count),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
