from __future__ import annotations

import inspect
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path.cwd()
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.runtime import runtime_utils


def _sample_function(*, temperature: float = 0.0, top_p: float = 1.0) -> None:
    _ = (temperature, top_p)


def main() -> int:
    iterations = 40000
    sample_count = 5
    elapsed_samples: list[float] = []
    signature_call_samples: list[int] = []
    declares_elapsed_samples: list[float] = []
    declares_signature_call_samples: list[int] = []
    first_declared_elapsed_samples: list[float] = []
    first_declared_signature_call_samples: list[int] = []
    original_signature = inspect.signature

    for _ in range(sample_count):
        runtime_utils.clear_callable_kwarg_signature_cache()
        signature_calls = 0

        def tracked_signature(callable_obj: Any) -> inspect.Signature:
            nonlocal signature_calls
            signature_calls += 1
            return original_signature(callable_obj)

        runtime_utils.inspect.signature = tracked_signature
        started = time.perf_counter()
        for index in range(iterations):
            keyword = "temperature" if index % 2 == 0 else "top_p"
            if not runtime_utils.callable_accepts_kwarg(_sample_function, keyword):
                raise SystemExit(f"unexpected missing kwarg: {keyword}")
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        signature_call_samples.append(signature_calls)

        runtime_utils.clear_callable_kwarg_signature_cache()
        declares_signature_calls = 0

        def tracked_declares_signature(callable_obj: Any) -> inspect.Signature:
            nonlocal declares_signature_calls
            declares_signature_calls += 1
            return original_signature(callable_obj)

        runtime_utils.inspect.signature = tracked_declares_signature
        declares_started = time.perf_counter()
        for index in range(iterations):
            keyword = "temperature" if index % 2 == 0 else "missing"
            expected = keyword == "temperature"
            if runtime_utils.callable_declares_kwarg(_sample_function, keyword) is not expected:
                raise SystemExit(f"unexpected kwarg declaration for: {keyword}")  # pragma: no cover
        declares_elapsed_samples.append((time.perf_counter() - declares_started) * 1000.0)
        declares_signature_call_samples.append(declares_signature_calls)

        runtime_utils.clear_callable_kwarg_signature_cache()
        first_declared_signature_calls = 0

        def tracked_first_declared_signature(callable_obj: Any) -> inspect.Signature:
            nonlocal first_declared_signature_calls
            first_declared_signature_calls += 1
            return original_signature(callable_obj)

        runtime_utils.inspect.signature = tracked_first_declared_signature
        first_declared_started = time.perf_counter()
        for index in range(iterations):
            keywords = ("missing", "temperature", "top_p") if index % 2 == 0 else ("missing", "top_p")
            expected = "temperature" if index % 2 == 0 else "top_p"
            if runtime_utils.first_declared_kwarg(_sample_function, keywords) != expected:
                raise SystemExit(f"unexpected first declared kwarg for: {keywords}")  # pragma: no cover
        first_declared_elapsed_samples.append((time.perf_counter() - first_declared_started) * 1000.0)
        first_declared_signature_call_samples.append(first_declared_signature_calls)

    runtime_utils.inspect.signature = original_signature
    runtime_utils.clear_callable_kwarg_signature_cache()

    metrics = {
        "elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "inspect_signature_calls_mean": statistics.fmean(signature_call_samples),
        "declares_elapsed_ms_mean": statistics.fmean(declares_elapsed_samples),
        "declares_signature_calls_mean": statistics.fmean(declares_signature_call_samples),
        "first_declared_elapsed_ms_mean": statistics.fmean(first_declared_elapsed_samples),
        "first_declared_signature_calls_mean": statistics.fmean(first_declared_signature_call_samples),
        "iterations_per_sample": float(iterations),
        "sample_count": float(sample_count),
    }
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
