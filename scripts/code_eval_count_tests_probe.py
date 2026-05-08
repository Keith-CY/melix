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


def _build_syntax_error_tests(line_count: int) -> str:
    body = "\n".join(
        f"assert value_{index} == {index}" if index % 3 else "   "
        for index in range(line_count)
    )
    return f"def broken(:\n{body}"


def _build_no_assert_tests(line_count: int) -> str:
    body = "\n".join(
        f"value_{index} = candidate({index})" if index % 4 else "\t"
        for index in range(line_count)
    )
    return "def check(candidate):\n" + body + "\ncheck(identity)"


def _expected_nonblank_lines(test_code: str) -> int:
    return sum(1 for line in test_code.splitlines() if line.strip())


def _run_sample(syntax_tests: str, no_assert_tests: str, iterations: int) -> tuple[float, int, int]:
    started = time.perf_counter()
    syntax_count = 0
    no_assert_count = 0
    for _ in range(iterations):
        syntax_count = code_eval_runner._count_tests(syntax_tests)
        no_assert_count = code_eval_runner._count_tests(no_assert_tests)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return elapsed_ms, syntax_count, no_assert_count


def main() -> int:
    line_count = 8000
    iterations = 25
    sample_count = 7
    syntax_tests = _build_syntax_error_tests(line_count)
    no_assert_tests = _build_no_assert_tests(line_count)
    expected_syntax_count = _expected_nonblank_lines(syntax_tests)
    expected_no_assert_count = _expected_nonblank_lines(no_assert_tests)

    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    syntax_count = 0
    no_assert_count = 0
    for _ in range(sample_count):
        tracemalloc.start()
        elapsed_ms, syntax_count, no_assert_count = _run_sample(
            syntax_tests, no_assert_tests, iterations
        )
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if syntax_count != expected_syntax_count:
            raise SystemExit(
                f"unexpected syntax fallback count: {syntax_count} != {expected_syntax_count}"
            )
        if no_assert_count != expected_no_assert_count:
            raise SystemExit(
                f"unexpected no-assert fallback count: {no_assert_count} != {expected_no_assert_count}"
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
                "syntax_count": float(syntax_count),
                "no_assert_count": float(no_assert_count),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
