#!/usr/bin/env python3
from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path.cwd()
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.engine import code_eval_runner  # noqa: E402


def _run_sample(iterations: int) -> tuple[float, int, int, int]:
    if hasattr(code_eval_runner._runner_script, "cache_clear"):
        code_eval_runner._runner_script.cache_clear()

    original_dedent = code_eval_runner.textwrap.dedent
    dedent_calls = 0

    def tracked_dedent(text: str) -> str:
        nonlocal dedent_calls
        dedent_calls += 1
        return original_dedent(text)

    code_eval_runner.textwrap.dedent = tracked_dedent
    try:
        started = time.perf_counter()
        checksum = 0
        script_id = None
        reused_identity = 1
        for _ in range(iterations):
            script = code_eval_runner._runner_script()
            if "def main() -> int:" not in script or not script.endswith("\n"):
                raise SystemExit("unexpected runner script payload")
            checksum += len(script)
            current_id = id(script)
            if script_id is None:
                script_id = current_id
            elif current_id != script_id:
                reused_identity = 0
        elapsed_ms = (time.perf_counter() - started) * 1000.0
    finally:
        code_eval_runner.textwrap.dedent = original_dedent
        if hasattr(code_eval_runner._runner_script, "cache_clear"):
            code_eval_runner._runner_script.cache_clear()

    return elapsed_ms, dedent_calls, checksum, reused_identity


def _measure_config_load(iterations: int) -> tuple[float, int]:
    script = code_eval_runner._runner_script()
    namespace: dict[str, object] = {"__name__": "melix_runner_probe"}
    exec(compile(script, "<melix-runner>", "exec"), namespace)
    load_config = namespace["_load_config"]
    payload = {
        "memory_limit_mb": 256,
        "stdio_limit_bytes": 32768,
        "payload_path": "/tmp/payload.json",
        "candidate_path": "/tmp/candidate.py",
        "entry_point": "",
        "test_code": "assert add(1, 2) == 3\n" * 50,
    }
    with tempfile.TemporaryDirectory(prefix="melix-code-eval-config-probe-") as temp_dir:
        config_path = Path(temp_dir) / "config.json"
        config_path.write_text(json.dumps(payload), encoding="utf-8")
        started = time.perf_counter()
        checksum = 0
        for _ in range(iterations):
            loaded = load_config(config_path)
            checksum += len(str(loaded["test_code"]))
        elapsed_ms = (time.perf_counter() - started) * 1000.0
    return elapsed_ms, checksum


def main() -> int:
    iterations = 20000
    config_iterations = 5000
    sample_count = 7
    elapsed_samples: list[float] = []
    dedent_calls: list[float] = []
    peak_samples: list[float] = []
    identity_reuse: list[float] = []
    config_load_samples: list[float] = []
    checksum = 0
    config_checksum = 0

    for _ in range(sample_count):
        tracemalloc.start()
        elapsed_ms, calls, checksum, reused_identity = _run_sample(iterations)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        config_elapsed_ms, config_checksum = _measure_config_load(config_iterations)
        elapsed_samples.append(elapsed_ms)
        dedent_calls.append(float(calls))
        peak_samples.append(float(peak))
        identity_reuse.append(float(reused_identity))
        config_load_samples.append(config_elapsed_ms)

    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(elapsed_samples),
                "dedent_calls_mean": statistics.fmean(dedent_calls),
                "peak_bytes_mean": statistics.fmean(peak_samples),
                "identity_reuse_mean": statistics.fmean(identity_reuse),
                "config_load_elapsed_ms_mean": statistics.fmean(config_load_samples),
                "iteration_count": float(iterations),
                "config_load_iteration_count": float(config_iterations),
                "sample_count": float(sample_count),
                "checksum": float(checksum + config_checksum),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
