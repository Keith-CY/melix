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


def _compatibility_payload(index: int) -> tuple[dict[str, Any], bool]:
    mode = index % 5
    if mode == 0:
        return {
            "id": "plain/model",
            "tags": ["Text-Generation", "MLX", object()],
            "library_name": "transformers",
            "cardData": {},
        }, True
    if mode == 1:
        return {
            "id": "plain/model",
            "tags": ["Text-Generation", object()],
            "library_name": "mlx",
            "cardData": {},
        }, True
    if mode == 2:
        return {
            "id": "owner/model-mlx-suffix",
            "tags": ["Text-Generation", object()],
            "library_name": "transformers",
            "cardData": {},
        }, True
    if mode == 3:
        return {
            "id": "plain/model",
            "tags": ["Text-Generation", object()],
            "library_name": "transformers",
            "cardData": {"tags": ["MLX", object()]},
        }, True
    return {
        "id": "plain/model",
        "tags": ["Text-Generation", object()],
        "library_name": "transformers",
        "cardData": {"tags": ["audio", object()]},
    }, False


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


def _run_compatibility_sample(iterations: int) -> tuple[float, int]:
    started = time.perf_counter()
    matched = 0
    for index in range(iterations):
        payload, expected = _compatibility_payload(index)
        compatible = hub_catalog._payload_is_mlx_compatible(payload)
        if compatible != expected:
            raise SystemExit(f"unexpected mlx compatibility at {index}: {compatible} != {expected}")
        if compatible:
            matched += 1
    return (time.perf_counter() - started) * 1000.0, matched


def main() -> int:
    iterations = int(os.environ.get("MELIX_HUB_CATALOG_SIZE_HINT_ITERATIONS", "200000"))
    compatibility_iterations = int(
        os.environ.get("MELIX_HUB_CATALOG_COMPATIBILITY_ITERATIONS", str(iterations))
    )
    sample_count = int(os.environ.get("MELIX_HUB_CATALOG_SIZE_HINT_SAMPLES", "5"))
    elapsed_samples: list[float] = []
    peak_samples: list[int] = []
    call_samples: list[int] = []
    compatibility_elapsed_samples: list[float] = []
    compatibility_matched_samples: list[int] = []
    checksum = 0
    matched = 0

    for _ in range(sample_count):
        tracemalloc.start()
        elapsed_ms, checksum, matched, calls = _run_sample(iterations)
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        compatibility_elapsed_ms, compatibility_matched = _run_compatibility_sample(
            compatibility_iterations
        )
        elapsed_samples.append(elapsed_ms)
        peak_samples.append(peak_bytes)
        call_samples.append(calls)
        compatibility_elapsed_samples.append(compatibility_elapsed_ms)
        compatibility_matched_samples.append(compatibility_matched)

    metrics = {
        "elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "peak_bytes_mean": statistics.fmean(peak_samples),
        "size_hint_calls_mean": statistics.fmean(call_samples),
        "matched_hint_count": float(matched),
        "payload_compatibility_elapsed_ms_mean": statistics.fmean(compatibility_elapsed_samples),
        "payload_compatibility_matched_count": float(compatibility_matched_samples[-1]),
        "payload_compatibility_calls_mean": float(compatibility_iterations),
        "checksum": float(checksum),
        "sample_count": float(sample_count),
    }
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
