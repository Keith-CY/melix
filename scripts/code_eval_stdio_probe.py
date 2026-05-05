from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
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


def main() -> None:
    byte_limit = 4096
    iterations = 3000
    with tempfile.TemporaryDirectory(prefix="melix-code-eval-stdio-probe-") as temp_dir:
        temp_root = Path(temp_dir)
        stdout_path = temp_root / "stdout.txt"
        stderr_path = temp_root / "stderr.txt"
        stdout_path.write_text("x" * (byte_limit * 4), encoding="utf-8")
        stderr_path.write_text("warning\n" * 128, encoding="utf-8")
        print(json.dumps(_measure_new(stdout_path, stderr_path, byte_limit=byte_limit, iterations=iterations), sort_keys=True))


if __name__ == "__main__":
    main()
