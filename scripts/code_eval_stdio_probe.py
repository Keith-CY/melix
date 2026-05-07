from __future__ import annotations

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

from worker.engine import code_eval_runner


def _measure_new(stdout_path: Path, stderr_path: Path, *, byte_limit: int, iterations: int) -> dict[str, float]:
    elapsed_samples: list[float] = []
    tail_lengths: list[float] = []
    output_limit_flags: list[float] = []
    for _ in range(5):
        start = time.perf_counter()
        stdout_tail = ""
        stderr_tail = ""
        output_limit_exceeded = False
        for _iteration in range(iterations):
            stdout_tail, stdout_size = code_eval_runner._read_limited_stdio(stdout_path, byte_limit)
            stderr_tail, stderr_size = code_eval_runner._read_limited_stdio(stderr_path, byte_limit)
            output_limit_exceeded = stdout_size >= byte_limit or stderr_size >= byte_limit
        elapsed_samples.append((time.perf_counter() - start) * 1000)
        tail_lengths.append(float(len(stdout_tail) + len(stderr_tail)))
        output_limit_flags.append(1.0 if output_limit_exceeded else 0.0)
    return {
        "elapsed_ms_mean": statistics.mean(elapsed_samples),
        "stdio_stat_calls_mean": 2.0 * iterations,
        "tail_chars_mean": statistics.mean(tail_lengths),
        "output_limit_exceeded_mean": statistics.mean(output_limit_flags),
        "iteration_count": float(iterations),
    }


def _measure_sandbox_profiles(temp_root: Path, *, iterations: int) -> dict[str, float]:
    elapsed_samples: list[float] = []
    profile_lengths: list[float] = []
    cache_clear = getattr(code_eval_runner._sandbox_static_profile_fragments, "cache_clear", None)
    for sample_index in range(5):
        if cache_clear is not None:
            cache_clear()
        start = time.perf_counter()
        profile = ""
        for iteration in range(iterations):
            profile = code_eval_runner._sandbox_profile(
                temp_root=temp_root / f"sample-{sample_index}" / f"run-{iteration}"
            )
        elapsed_samples.append((time.perf_counter() - start) * 1000)
        profile_lengths.append(float(len(profile)))
    if cache_clear is not None:
        cache_clear()
    return {
        "sandbox_profile_elapsed_ms_mean": statistics.mean(elapsed_samples),
        "sandbox_profile_static_builds_mean": 1.0 if cache_clear is not None else float(iterations),
        "sandbox_profile_length_mean": statistics.mean(profile_lengths),
        "sandbox_profile_iteration_count": float(iterations),
    }


def _measure_count_tests(*, line_count: int) -> dict[str, float]:
    syntax_error_input = "\n".join(f"assert value_{index}" for index in range(line_count))
    parseable_no_assert_input = "\n".join(f"value_{index} = {index}" for index in range(line_count))
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    result_samples: list[float] = []
    for test_code in (syntax_error_input, parseable_no_assert_input):
        for _ in range(5):
            tracemalloc.start()
            start = time.perf_counter()
            result = code_eval_runner._count_tests(test_code)
            elapsed_samples.append((time.perf_counter() - start) * 1000)
            _current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            result_samples.append(float(result))
            peak_samples.append(float(peak))
    return {
        "count_tests_elapsed_ms_mean": statistics.mean(elapsed_samples),
        "count_tests_peak_bytes_mean": statistics.mean(peak_samples),
        "count_tests_line_count": float(line_count),
        "count_tests_result_mean": statistics.mean(result_samples),
    }


def main() -> None:
    byte_limit = 4096
    iterations = 3000
    with tempfile.TemporaryDirectory(prefix="melix-code-eval-stdio-probe-") as temp_dir:
        temp_root = Path(temp_dir)
        stdout_path = temp_root / "stdout.txt"
        stderr_path = temp_root / "stderr.txt"
        stdout_path.write_text("x" * (byte_limit * 4), encoding="utf-8")
        stderr_path.write_text("warning\n" * 128, encoding="utf-8")
        metrics = _measure_new(stdout_path, stderr_path, byte_limit=byte_limit, iterations=iterations)
        metrics.update(_measure_sandbox_profiles(temp_root, iterations=1500))
        metrics.update(_measure_count_tests(line_count=20_000))
        print(json.dumps(metrics, sort_keys=True))


if __name__ == "__main__":
    main()
