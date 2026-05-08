#!/usr/bin/env python3
from __future__ import annotations

import json
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path.cwd()
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.engine import code_eval_runner  # noqa: E402


def _build_test_code(line_count: int) -> str:
    lines = []
    for index in range(line_count):
        if index % 5 == 0:
            lines.append("   ")
        elif index % 7 == 0:
            lines.append(f"# comment {index}")
        else:
            lines.append(f"value_{index} = candidate({index})")
    return "\n".join(lines)


def main() -> None:
    line_count = 60_000
    sample_count = 7
    test_code = _build_test_code(line_count)
    expected_nonblank = sum(1 for line in test_code.splitlines() if line.strip())
    elapsed_ms: list[float] = []
    peak_bytes: list[float] = []
    counted_lines: list[float] = []

    for _ in range(sample_count):
        tracemalloc.start()
        started = time.perf_counter()
        counted = code_eval_runner._count_nonblank_test_lines(test_code)
        elapsed_ms.append((time.perf_counter() - started) * 1000.0)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_bytes.append(float(peak))
        if counted != expected_nonblank:
            raise SystemExit(f"unexpected nonblank count: {counted} != {expected_nonblank}")
        counted_lines.append(float(counted))

    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(elapsed_ms),
                "peak_bytes_mean": statistics.fmean(peak_bytes),
                "line_count": float(line_count),
                "nonblank_line_count_mean": statistics.fmean(counted_lines),
                "sample_count": float(sample_count),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
