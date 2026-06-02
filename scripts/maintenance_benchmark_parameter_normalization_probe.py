#!/usr/bin/env python3
"""Measure benchmark parameter normalization conversion reuse."""

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

from worker.engine.maintenance_core import MaintenanceCore  # noqa: E402


class CountedInt:
    def __init__(self, value: int) -> None:
        self.value = value
        self.calls = 0

    def __int__(self) -> int:
        self.calls += 1
        return self.value


class CountedString:
    def __init__(self, value: str) -> None:
        self.value = value
        self.calls = 0

    def __str__(self) -> str:
        self.calls += 1
        return self.value


def _int_values(value_count: int) -> list[CountedInt]:
    return [CountedInt((index % 97) - 12) for index in range(value_count)]


def _string_values(value_count: int) -> list[CountedString]:
    variants = (" cold ", "", " warm", "default ", " structured ", "cold")
    return [CountedString(variants[index % len(variants)]) for index in range(value_count)]


def _native_int_values(value_count: int) -> list[int]:
    return [(index % 97) - 12 for index in range(value_count)]


def _native_string_values(value_count: int) -> list[str]:
    variants = (" cold ", "", " warm", "default ", " structured ", "cold")
    return [variants[index % len(variants)] for index in range(value_count)]


def _run_sample(value_count: int, iterations: int) -> tuple[float, int, int, int, int, int]:
    int_conversion_calls = 0
    string_conversion_calls = 0
    int_value_total = 0
    string_value_total = 0
    checksum = 0
    started = time.perf_counter()
    for _ in range(iterations):
        ints = _int_values(value_count)
        strings = _string_values(value_count)
        positive_values = MaintenanceCore._positive_sorted_values(ints, default=(32,))
        normalized_strings = MaintenanceCore._normalized_string_values(strings, default=("default",))
        if positive_values[0] <= 0 or normalized_strings != ("cold", "default", "structured", "warm"):
            raise SystemExit("unexpected benchmark parameter normalization output")
        int_conversion_calls += sum(value.calls for value in ints)
        string_conversion_calls += sum(value.calls for value in strings)
        int_value_total += len(ints)
        string_value_total += len(strings)
        checksum += len(positive_values) + len(normalized_strings)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return (
        elapsed_ms,
        int_conversion_calls,
        string_conversion_calls,
        int_value_total,
        string_value_total,
        checksum,
    )


def _run_native_sample(value_count: int, iterations: int) -> tuple[float, int]:
    checksum = 0
    started = time.perf_counter()
    for _ in range(iterations):
        positive_values = MaintenanceCore._positive_sorted_values(
            _native_int_values(value_count),
            default=(32,),
        )
        normalized_strings = MaintenanceCore._normalized_string_values(
            _native_string_values(value_count),
            default=("default",),
        )
        if positive_values[0] <= 0 or normalized_strings != ("cold", "default", "structured", "warm"):
            raise SystemExit("unexpected native benchmark parameter normalization output")
        checksum += len(positive_values) + len(normalized_strings)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return elapsed_ms, checksum


def main() -> int:
    value_count = int(os.environ.get("MELIX_MAINTENANCE_PARAMETER_PROBE_VALUE_COUNT", "3000"))
    iterations = int(os.environ.get("MELIX_MAINTENANCE_PARAMETER_PROBE_ITERATIONS", "80"))
    sample_count = int(os.environ.get("MELIX_MAINTENANCE_PARAMETER_PROBE_SAMPLES", "5"))
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    int_call_samples: list[float] = []
    string_call_samples: list[float] = []
    calls_per_value_samples: list[float] = []
    native_elapsed_samples: list[float] = []
    checksum = 0
    native_checksum = 0

    for _ in range(sample_count):
        tracemalloc.start()
        (
            elapsed_ms,
            int_calls,
            string_calls,
            int_values,
            string_values,
            checksum,
        ) = _run_sample(value_count, iterations)
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        elapsed_samples.append(elapsed_ms)
        peak_samples.append(float(peak_bytes))
        int_call_samples.append(float(int_calls))
        string_call_samples.append(float(string_calls))
        calls_per_value_samples.append((int_calls + string_calls) / (int_values + string_values))
        native_elapsed_ms, native_checksum = _run_native_sample(value_count, iterations)
        native_elapsed_samples.append(native_elapsed_ms)

    print(
        json.dumps(
            {
                "calls_per_value_mean": round(statistics.fmean(calls_per_value_samples), 6),
                "checksum": float(checksum),
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "int_conversion_calls_mean": round(statistics.fmean(int_call_samples), 6),
                "iteration_count": float(iterations),
                "native_checksum": float(native_checksum),
                "native_elapsed_ms_mean": round(statistics.fmean(native_elapsed_samples), 6),
                "peak_bytes_mean": round(statistics.fmean(peak_samples), 6),
                "sample_count": float(sample_count),
                "string_conversion_calls_mean": round(statistics.fmean(string_call_samples), 6),
                "value_count": float(value_count),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
