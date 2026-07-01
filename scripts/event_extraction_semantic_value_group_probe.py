#!/usr/bin/env python3
"""Measure event-extraction semantic action value-group reuse and matching."""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.productization import event_extraction as event_extraction_module  # noqa: E402


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return max(1, int(value))


def _matching_candidates(value_count: int) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for index in range(value_count):
        candidates.append(
            {
                "gold_indices": (index,),
                "pred_indices": (index,),
                "score": 0.72 + (index % 5) * 0.01,
            }
        )
    for left in range(0, max(0, value_count - 1), 2):
        right = left + 1
        candidates.append(
            {
                "gold_indices": (left, right),
                "pred_indices": (left,),
                "score": 0.82,
            }
        )
        candidates.append(
            {
                "gold_indices": (left,),
                "pred_indices": (left, right),
                "score": 0.82,
            }
        )
    candidates.extend(
        [
            {"gold_indices": (value_count + 7,), "pred_indices": (0,), "score": 1.0},
            {"gold_indices": (0,), "pred_indices": (value_count + 7,), "score": 1.0},
        ]
    )
    return candidates


def _run_probe(
    *,
    counts: Iterable[int],
    matching_counts: Iterable[int],
    iterations: int,
    matching_iterations: int,
    samples: int,
) -> dict[str, float]:
    original_combinations = event_extraction_module.combinations
    elapsed_ms: list[float] = []
    peak_bytes: list[float] = []
    combination_calls: list[float] = []
    matching_elapsed_ms: list[float] = []
    group_count = 0
    matching_candidate_count = 0
    matching_result_count = 0
    checksum = 0
    matching_checksum = 0

    def counted_combinations(*args: object, **kwargs: object) -> object:
        nonlocal current_combination_calls
        current_combination_calls += 1
        return original_combinations(*args, **kwargs)

    event_extraction_module.combinations = counted_combinations
    try:
        for _sample_index in range(samples):
            current_combination_calls = 0
            cache_clear = getattr(event_extraction_module._semantic_value_groups, "cache_clear", None)
            if cache_clear is not None:
                cache_clear()
            tracemalloc.start()
            started = time.perf_counter()
            sample_group_count = 0
            sample_checksum = 0
            for _ in range(iterations):
                for value_count in counts:
                    groups = event_extraction_module._semantic_value_groups(value_count)
                    sample_group_count += len(groups)
                    sample_checksum += sum(sum(group) + len(group) * 17 for group in groups)
            elapsed_ms.append((time.perf_counter() - started) * 1000.0)
            _current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peak_bytes.append(float(peak))
            combination_calls.append(float(current_combination_calls))
            group_count = sample_group_count
            checksum += sample_checksum

            started = time.perf_counter()
            sample_matching_checksum = 0
            sample_candidate_count = 0
            sample_result_count = 0
            for _ in range(matching_iterations):
                for value_count in matching_counts:
                    candidates = _matching_candidates(value_count)
                    matches = event_extraction_module._maximum_weight_semantic_value_group_matching(
                        candidates,
                        gold_count=value_count,
                        pred_count=value_count,
                    )
                    sample_candidate_count += len(candidates)
                    sample_result_count += len(matches)
                    for match in matches:
                        sample_matching_checksum += int(float(match.get("score", 0.0) or 0.0) * 1000)
                        sample_matching_checksum += sum(match.get("gold_indices", ()))  # type: ignore[arg-type]
                        sample_matching_checksum += sum(match.get("pred_indices", ()))  # type: ignore[arg-type]
            matching_elapsed_ms.append((time.perf_counter() - started) * 1000.0)
            matching_candidate_count = sample_candidate_count
            matching_result_count = sample_result_count
            matching_checksum += sample_matching_checksum
    finally:
        event_extraction_module.combinations = original_combinations

    return {
        "elapsed_ms_mean": statistics.fmean(elapsed_ms),
        "elapsed_ms_min": min(elapsed_ms),
        "peak_bytes_mean": statistics.fmean(peak_bytes),
        "combination_build_calls_mean": statistics.fmean(combination_calls),
        "matching_elapsed_ms_mean": statistics.fmean(matching_elapsed_ms),
        "matching_elapsed_ms_min": min(matching_elapsed_ms),
        "matching_candidate_count_per_sample": float(matching_candidate_count),
        "matching_result_count_per_sample": float(matching_result_count),
        "iterations_per_sample": float(iterations),
        "matching_iterations_per_sample": float(matching_iterations),
        "sample_count": float(samples),
        "value_count_max": float(max(counts)),
        "group_count_per_sample": float(group_count),
        "checksum": float(checksum),
        "matching_checksum": float(matching_checksum),
    }


def main() -> int:
    counts = tuple(
        int(part)
        for part in os.getenv("MELIX_EVENT_SEMANTIC_GROUP_PROBE_COUNTS", "4,8,12,16").split(",")
        if part.strip()
    )
    matching_counts = tuple(
        int(part)
        for part in os.getenv("MELIX_EVENT_SEMANTIC_MATCHING_PROBE_COUNTS", "4,6,8").split(",")
        if part.strip()
    )
    metrics = _run_probe(
        counts=counts,
        matching_counts=matching_counts,
        iterations=_env_int("MELIX_EVENT_SEMANTIC_GROUP_PROBE_ITERATIONS", 20000),
        matching_iterations=_env_int("MELIX_EVENT_SEMANTIC_MATCHING_PROBE_ITERATIONS", 100),
        samples=_env_int("MELIX_EVENT_SEMANTIC_GROUP_PROBE_SAMPLES", 5),
    )
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
