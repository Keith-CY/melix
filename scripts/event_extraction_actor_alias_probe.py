#!/usr/bin/env python3
"""Measure cached group-actor alias expansion in event-extraction semantic scoring."""
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


def _actor_values(value_count: int) -> list[str]:
    aliases = ["我们", "双方", "咱们", "咱俩", "我俩"]
    normalized_aliases = ["我 们", "双 方", "咱 们", "咱 俩", "我 俩", "两 人", "二 人"]
    if value_count <= len(normalized_aliases):
        return [normalized_aliases[index % len(normalized_aliases)] for index in range(value_count)]

    values: list[str] = []
    for index in range(value_count):
        if index % 90 == 0:
            values.append(normalized_aliases[(index // 90) % len(normalized_aliases)])
        elif index % 3 == 0:
            values.append(aliases[index % len(aliases)])
        elif index % 3 == 1:
            values.append(f"speaker_{1 + (index % 2)}")
        else:
            values.append(f"actor-{index}")
    return values


def _run_probe(*, value_count: int, iterations: int, samples: int) -> dict[str, float]:
    original_normalize = event_extraction_module._normalize_similarity_text
    normalize_calls = 0

    def counted_normalize(value: str) -> str:
        nonlocal normalize_calls
        normalize_calls += 1
        return original_normalize(value)

    event_extraction_module._normalize_similarity_text = counted_normalize
    event = {"actor": _actor_values(value_count)}
    elapsed_ms: list[float] = []
    peak_bytes: list[float] = []
    normalize_calls_per_sample: list[float] = []
    output_lengths: list[int] = []
    try:
        for _ in range(samples):
            normalize_calls = 0
            tracemalloc.start()
            started = time.perf_counter()
            output_length = 0
            for _iteration in range(iterations):
                output_length += len(event_extraction_module._semantic_field_values("actor", event))
            elapsed_ms.append((time.perf_counter() - started) * 1000.0)
            _current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peak_bytes.append(float(peak))
            normalize_calls_per_sample.append(float(normalize_calls))
            output_lengths.append(output_length)
    finally:
        event_extraction_module._normalize_similarity_text = original_normalize
        if tracemalloc.is_tracing():
            tracemalloc.stop()

    expected_output_length = output_lengths[0]
    if any(length != expected_output_length for length in output_lengths):
        raise AssertionError(f"unstable output lengths: {output_lengths}")

    return {
        "elapsed_ms_mean": statistics.fmean(elapsed_ms),
        "elapsed_ms_min": min(elapsed_ms),
        "peak_bytes_mean": statistics.fmean(peak_bytes),
        "normalize_calls_mean": statistics.fmean(normalize_calls_per_sample),
        "value_count": float(value_count),
        "iterations_per_sample": float(iterations),
        "sample_count": float(samples),
        "output_length_per_sample": float(expected_output_length),
    }


def main() -> int:
    value_count = _env_int("MELIX_EVENT_ACTOR_ALIAS_PROBE_VALUE_COUNT", 200)
    iterations = _env_int("MELIX_EVENT_ACTOR_ALIAS_PROBE_ITERATIONS", 200)
    samples = _env_int("MELIX_EVENT_ACTOR_ALIAS_PROBE_SAMPLES", 5)
    print(
        json.dumps(
            _run_probe(value_count=value_count, iterations=iterations, samples=samples),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
