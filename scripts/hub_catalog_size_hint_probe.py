from __future__ import annotations

import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

REPO_ROOT = Path(os.environ.get("MELIX_HUB_CATALOG_SIZE_HINT_REPO_ROOT") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

import worker.model_ops.hub_catalog as hub_catalog


def _payload(index: int) -> tuple[dict[str, Any], int]:
    value = 128 + (index % 2048)
    mode = index % 5
    if mode == 0:
        return {"cardData": {}}, 0
    if mode == 1:
        return {"cardData": {"model_size": f"Model size: {value} MB"}}, value * 1024 * 1024
    if mode == 2:
        return {"cardData": {}, "readme": f"README\nMODEL SIZE | {value} kb\nother metadata"}, value * 1024
    if mode == 3:
        return {"cardData": {}, "description": f"description only {value} MB"}, 0
    return {
        "cardData": {"description": f"training corpus {value} kb"},
        "description": f"tokenizer assets {value} MB",
        "readme": f"adapter notes {value} MB",
    }, 0


def _run_sample(iterations: int) -> tuple[float, int, int, int]:
    calls = 0
    original = hub_catalog._size_hint_from_text

    def tracked_size_hint(text: str, *, allow_bare: bool) -> int:
        nonlocal calls
        calls += 1
        return original(text, allow_bare=allow_bare)

    hub_catalog._size_hint_from_text = tracked_size_hint
    try:
        started = time.perf_counter()
        checksum = 0
        matched = 0
        for index in range(iterations):
            payload, expected = _payload(index)
            parsed = hub_catalog._size_hint_bytes(payload)
            if parsed != expected:
                raise SystemExit(f"unexpected size hint at {index}: {parsed} != {expected}")
            checksum ^= parsed
            if parsed:
                matched += 1
        return (time.perf_counter() - started) * 1000.0, checksum, matched, calls
    finally:
        hub_catalog._size_hint_from_text = original


def main() -> int:
    iterations = int(os.environ.get("MELIX_HUB_CATALOG_SIZE_HINT_ITERATIONS", "200000"))
    sample_count = int(os.environ.get("MELIX_HUB_CATALOG_SIZE_HINT_SAMPLES", "5"))
    elapsed_samples: list[float] = []
    peak_samples: list[int] = []
    call_samples: list[int] = []
    checksum = 0
    matched = 0

    for _ in range(sample_count):
        tracemalloc.start()
        elapsed_ms, checksum, matched, calls = _run_sample(iterations)
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        elapsed_samples.append(elapsed_ms)
        peak_samples.append(peak_bytes)
        call_samples.append(calls)

    metrics = {
        "elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "peak_bytes_mean": statistics.fmean(peak_samples),
        "size_hint_calls_mean": statistics.fmean(call_samples),
        "matched_hint_count": float(matched),
        "checksum": float(checksum),
        "sample_count": float(sample_count),
    }
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
