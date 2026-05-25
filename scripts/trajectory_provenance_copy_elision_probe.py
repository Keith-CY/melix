#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import os
import statistics
import time
import tracemalloc
from pathlib import Path
from typing import Any, Callable

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKER_ROOT = REPO_ROOT / "services" / "mlx-worker-python"
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from worker.trajectory_provenance import (  # noqa: E402
    _copy_trajectory_provenance_value,
    normalize_trajectory_provenance,
)


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _build_provenance(component_count: int) -> dict[str, Any]:
    return {
        "trajectory_dataset_id": "agentic-snapshot",
        "trajectory_dataset_version": "2026-05-25",
        "trajectory_schema_version": "melix.agentic_tool_trace.v1",
        "trajectory_trace_digest": "sha256:fixture",
        "trajectory_quality_metrics": {
            "reward_coverage_count": component_count,
            "components": [
                {
                    "name": f"component-{index}",
                    "score": float(index % 7) / 7.0,
                    "passed": index % 3 != 0,
                    "labels": ["agentic", "trajectory", str(index % 5)],
                }
                for index in range(component_count)
            ],
        },
        "agentic_sft_token_metrics": {
            "estimator": "fixture-tokenizer",
            "source_trace_count": component_count,
            "trace_tokens": component_count * 37,
            "tool_call_tokens": component_count * 11,
            "observation_tokens": component_count * 13,
            "final_answer_tokens": component_count * 5,
        },
    }


def _baseline_normalize(provenance: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for field in (
        "trajectory_dataset_id",
        "trajectory_dataset_version",
        "trajectory_schema_version",
        "trajectory_snapshot_manifest_path",
        "trajectory_split",
        "trajectory_trace_digest",
        "trajectory_toolset_version",
        "trajectory_registry_schema_version",
        "trajectory_reward_policy_id",
        "trajectory_leakage_policy_id",
        "trajectory_package_path",
        "trajectory_quality_metrics",
        "agentic_sft_token_metrics",
    ):
        value = provenance.get(field)
        if value in ("", None):
            continue
        if isinstance(value, (dict, list)):
            normalized[field] = copy.deepcopy(value)
        else:
            normalized[field] = value
    return normalized


def _measure(func: Callable[[dict[str, Any]], dict[str, Any]], provenance: dict[str, Any], iterations: int) -> tuple[float, int]:
    tracemalloc.start()
    start = time.perf_counter()
    checksum = 0
    for _ in range(iterations):
        normalized = func(provenance)
        checksum += int(normalized["trajectory_quality_metrics"]["reward_coverage_count"])
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    if checksum != provenance["trajectory_quality_metrics"]["reward_coverage_count"] * iterations:
        raise RuntimeError("probe checksum mismatch")
    return elapsed_ms, peak_bytes


def _mean(values: list[float]) -> float:
    return float(statistics.fmean(values)) if values else 0.0


def main() -> int:
    iterations = _int_env("MELIX_TRAJECTORY_PROVENANCE_PROBE_ITERATIONS", 2000)
    samples = _int_env("MELIX_TRAJECTORY_PROVENANCE_PROBE_SAMPLES", 5)
    component_count = _int_env("MELIX_TRAJECTORY_PROVENANCE_PROBE_COMPONENTS", 64)
    provenance = _build_provenance(component_count)

    baseline_ms: list[float] = []
    optimized_ms: list[float] = []
    baseline_peak: list[float] = []
    optimized_peak: list[float] = []

    copied = _copy_trajectory_provenance_value(provenance["trajectory_quality_metrics"])
    if copied is provenance["trajectory_quality_metrics"] or copied["components"] is provenance["trajectory_quality_metrics"]["components"]:
        raise RuntimeError("optimized copy did not isolate nested containers")

    for _ in range(samples):
        elapsed, peak = _measure(_baseline_normalize, provenance, iterations)
        baseline_ms.append(elapsed)
        baseline_peak.append(float(peak))
        elapsed, peak = _measure(normalize_trajectory_provenance, provenance, iterations)
        optimized_ms.append(elapsed)
        optimized_peak.append(float(peak))

    baseline_mean = _mean(baseline_ms)
    optimized_mean = _mean(optimized_ms)
    delta_ms = optimized_mean - baseline_mean
    speedup = baseline_mean / optimized_mean if optimized_mean > 0 else 0.0
    result = {
        "baseline_elapsed_ms_mean": baseline_mean,
        "optimized_elapsed_ms_mean": optimized_mean,
        "elapsed_ms_mean": optimized_mean,
        "delta_ms": delta_ms,
        "speedup": speedup,
        "baseline_peak_bytes_mean": _mean(baseline_peak),
        "optimized_peak_bytes_mean": _mean(optimized_peak),
        "peak_bytes_mean": _mean(optimized_peak),
        "sample_count": float(samples),
        "iteration_count": float(iterations),
        "component_count": float(component_count),
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
