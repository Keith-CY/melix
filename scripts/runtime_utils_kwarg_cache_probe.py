from __future__ import annotations

import inspect
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
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

    runtime_utils.inspect.signature = original_signature
    runtime_utils.clear_callable_kwarg_signature_cache()

    metrics = {
        "elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "inspect_signature_calls_mean": statistics.fmean(signature_call_samples),
        "iterations_per_sample": float(iterations),
        "sample_count": float(sample_count),
    }
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
