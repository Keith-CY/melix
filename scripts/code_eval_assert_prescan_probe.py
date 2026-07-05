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


def _build_comment_string_assert_tests(line_count: int) -> str:
    def line_for(index: int) -> str:
        remainder = index % 4
        if remainder == 0:
            return "\t"
        if remainder == 1:
            return f"# assert mention {index} should not force AST parsing"
        if remainder == 2:
            return f"message_{index} = 'assert mention {index}'"
        return f"value_{index} = candidate({index})"

    body = "\n".join(line_for(index) for index in range(line_count))
    return "def check(candidate):\n" + body + "\ncheck(identity)"


def _expected_nonblank_lines(test_code: str) -> int:
    return sum(1 for line in test_code.splitlines() if line.strip())


def main() -> int:
    line_count = 8000
    iterations = 25
    sample_count = 7
    test_code = _build_comment_string_assert_tests(line_count)
    expected_count = _expected_nonblank_lines(test_code)
    code_eval_runner._count_tests.cache_clear()

    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    nonblank_count = 0
    for _ in range(sample_count):
        code_eval_runner._count_tests.cache_clear()
        tracemalloc.start()
        started = time.perf_counter()
        for _index in range(iterations):
            nonblank_count = code_eval_runner._count_tests(test_code)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if nonblank_count != expected_count:
            raise SystemExit(
                f"unexpected assert-mention fallback count: {nonblank_count} != {expected_count}"
            )
        elapsed_samples.append(elapsed_ms)
        peak_samples.append(float(peak))

    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(elapsed_samples),
                "peak_bytes_mean": statistics.fmean(peak_samples),
                "line_count": float(line_count),
                "iteration_count": float(iterations),
                "sample_count": float(sample_count),
                "nonblank_count": float(nonblank_count),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
