#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import time
import tracemalloc
from typing import Any

from worker.productization.evaluation_final_result import (
    EvaluationProfileDefinition,
    score_final_result,
)


def _payload(key_count: int) -> tuple[str, str, tuple[str, ...]]:
    expected: dict[str, Any] = {}
    actual: dict[str, Any] = {}
    ignored_paths: list[str] = []
    for index in range(key_count):
        key = f"field_{index}"
        expected[key] = {
            "label": f"value-{index}",
            "scores": [index, index + 1, index + 2],
            "metadata": {
                "confidence": index / max(key_count, 1),
                "evidence": [f"source-{index}", f"source-{index + 1}"],
            },
        }
        actual[key] = {
            "label": expected[key]["label"] if index % 4 else "mismatch",
            "scores": expected[key]["scores"],
            "metadata": {
                "confidence": 0.0,
                "evidence": ["different-source"],
            },
        }
        ignored_paths.append(f"{key}.metadata")
    return json.dumps(expected), json.dumps(actual), tuple(ignored_paths)


def _run_once(*, key_count: int, iterations: int) -> tuple[float, float, float]:
    target, extracted, ignored_paths = _payload(key_count)
    profile = EvaluationProfileDefinition(
        profile_type="final_result",
        result_kind="json",
        extraction_mode="strict_full_response",
        scoring_mode="json_field_match",
        threshold=1.0,
        ignored_paths=ignored_paths,
    )
    checksum = 0.0
    tracemalloc.start()
    started = time.perf_counter()
    for _ in range(iterations):
        outcome = score_final_result(
            extracted_result=extracted,
            target=target,
            profile=profile,
        )
        if outcome.validation_status != "validated":
            raise AssertionError(outcome)
        checksum += outcome.typed_score
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return elapsed_ms, float(peak_bytes), checksum


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keys", type=int, default=2000)
    parser.add_argument("--iterations", type=int, default=40)
    parser.add_argument("--samples", type=int, default=5)
    args = parser.parse_args()

    samples = [
        _run_once(key_count=args.keys, iterations=args.iterations)
        for _ in range(args.samples)
    ]
    checksum = samples[-1][2]
    expected_checksum = args.iterations * 0.875
    if abs(checksum - expected_checksum) > 1e-9:
        raise AssertionError((checksum, expected_checksum))
    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(sample[0] for sample in samples),
                "peak_bytes_mean": statistics.fmean(sample[1] for sample in samples),
                "score_checksum": checksum,
                "key_count": float(args.keys),
                "iteration_count": float(args.iterations),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
