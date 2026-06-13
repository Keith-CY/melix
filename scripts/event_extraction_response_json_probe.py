#!/usr/bin/env python3
"""Synthetic probe for event-extraction response JSON parsing."""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path.cwd()
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.productization import event_extraction as event_extraction_module  # noqa: E402


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return max(1, int(value))


def _response(event_count: int, *, leading_whitespace: bool = True) -> str:
    events = [
        {
            "event_type": "delivery",
            "trigger": f"delivered-{index}",
            "arguments": {
                "actor": ["courier", f"team-{index % 8}"],
                "item": [f"crate-{index}"],
                "destination": [f"dock-{index % 13}"],
            },
        }
        for index in range(event_count)
    ]
    response = json.dumps({"events": events}, ensure_ascii=False, separators=(",", ":")) + "\n  "
    # Include leading and trailing whitespace to exercise the unfenced JSON
    # parser path without making json.loads perform its own leading scan.
    if leading_whitespace:
        return "   \n" + response
    return response


def _measure_response(response: str, *, event_count: int, iterations: int, samples: int) -> dict[str, float]:
    elapsed_ms: list[float] = []
    peak_bytes: list[float] = []
    checksum = 0
    for _ in range(samples):
        tracemalloc.start()
        started = time.perf_counter()
        for _index in range(iterations):
            payload = event_extraction_module._parse_response_json(response)
            events = payload.get("events")
            if not isinstance(events, list) or len(events) != event_count:
                raise AssertionError("event-extraction response JSON probe parsed an unexpected payload")
            checksum += len(events)
        elapsed_ms.append((time.perf_counter() - started) * 1000.0)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_bytes.append(float(peak))
    return {
        "elapsed_ms_mean": statistics.fmean(elapsed_ms),
        "peak_bytes_mean": statistics.fmean(peak_bytes),
        "checksum": float(checksum),
    }


def run_probe(*, event_count: int = 1600, iterations: int = 80, samples: int = 5) -> dict[str, float]:
    leading_metrics = _measure_response(
        _response(event_count), event_count=event_count, iterations=iterations, samples=samples
    )
    direct_metrics = _measure_response(
        _response(event_count, leading_whitespace=False),
        event_count=event_count,
        iterations=iterations,
        samples=samples,
    )
    return {
        "elapsed_ms_mean": leading_metrics["elapsed_ms_mean"],
        "peak_bytes_mean": leading_metrics["peak_bytes_mean"],
        "direct_elapsed_ms_mean": direct_metrics["elapsed_ms_mean"],
        "direct_peak_bytes_mean": direct_metrics["peak_bytes_mean"],
        "direct_checksum": direct_metrics["checksum"],
        "event_count": float(event_count),
        "iterations_per_sample": float(iterations),
        "sample_count": float(samples),
        "checksum": leading_metrics["checksum"],
    }


def main() -> int:
    metrics = run_probe(
        event_count=_env_int("MELIX_EVENT_RESPONSE_JSON_PROBE_EVENT_COUNT", 1600),
        iterations=_env_int("MELIX_EVENT_RESPONSE_JSON_PROBE_ITERATIONS", 80),
        samples=_env_int("MELIX_EVENT_RESPONSE_JSON_PROBE_SAMPLES", 5),
    )
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
