from __future__ import annotations

import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.model_ops.hub_catalog import _size_hint_from_text


def _text(index: int) -> tuple[str, bool, int]:
    value = 128 + (index % 2048)
    mode = index % 4
    if mode == 0:
        return f"{value} MB", True, value * 1024 * 1024
    if mode == 1:
        return f"Model size: {value} MB", False, value * 1024 * 1024
    if mode == 2:
        return f"README\nMODEL SIZE | {value} kb\nother metadata", False, value * 1024
    return f"description only {value} MB", False, 0


def _run_sample(iterations: int) -> tuple[float, int, int]:
    started = time.perf_counter()
    checksum = 0
    matched = 0
    for index in range(iterations):
        text, allow_bare, expected = _text(index)
        parsed = _size_hint_from_text(text, allow_bare=allow_bare)
        if parsed != expected:
            raise SystemExit(f"unexpected size hint at {index}: {parsed} != {expected}")
        checksum ^= parsed
        if parsed:
            matched += 1
    return (time.perf_counter() - started) * 1000.0, checksum, matched


def main() -> int:
    iterations = int(os.environ.get("MELIX_HUB_CATALOG_SIZE_HINT_ITERATIONS", "200000"))
    sample_count = int(os.environ.get("MELIX_HUB_CATALOG_SIZE_HINT_SAMPLES", "5"))
    elapsed_samples: list[float] = []
    peak_samples: list[int] = []
    checksum = 0
    matched = 0

    for _ in range(sample_count):
        tracemalloc.start()
        elapsed_ms, checksum, matched = _run_sample(iterations)
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        elapsed_samples.append(elapsed_ms)
        peak_samples.append(peak_bytes)

    metrics = {
        "elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "peak_bytes_mean": statistics.fmean(peak_samples),
        "size_hint_calls_mean": float(iterations),
        "matched_hint_count": float(matched),
        "checksum": float(checksum),
        "sample_count": float(sample_count),
    }
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
