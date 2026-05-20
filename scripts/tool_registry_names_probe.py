#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.runtime.tool_registry import BUILTIN_AGENTIC_TOOL_NAMES, built_in_tool_registry  # noqa: E402


def _measure(iterations: int, sample_count: int) -> dict[str, float]:
    registry = built_in_tool_registry()
    expected_names = BUILTIN_AGENTIC_TOOL_NAMES
    elapsed_samples: list[float] = []
    registry_factory_elapsed_samples: list[float] = []
    same_object_samples: list[float] = []
    checksum = 0

    for _ in range(sample_count):
        first_names = registry.names()
        same_object_count = 0
        started = time.perf_counter()
        for _index in range(iterations):
            names = registry.names()
            if names != expected_names:
                raise RuntimeError(f"unexpected tool names: {names!r}")
            if names is first_names:
                same_object_count += 1
            checksum += len(names)
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        same_object_samples.append(float(same_object_count))

        started = time.perf_counter()
        for _index in range(iterations):
            if built_in_tool_registry().names() != expected_names:  # pragma: no cover
                raise RuntimeError("built-in tool registry returned unexpected names")
            checksum += 1
        registry_factory_elapsed_samples.append((time.perf_counter() - started) * 1000.0)

    return {
        "elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "registry_factory_elapsed_ms_mean": statistics.fmean(registry_factory_elapsed_samples),
        "names_calls_mean": float(iterations),
        "same_names_object_calls_mean": statistics.fmean(same_object_samples),
        "checksum": float(checksum),
        "iterations": float(iterations),
        "sample_count": float(sample_count),
    }


def main() -> int:
    iterations = int(os.environ.get("MELIX_TOOL_REGISTRY_NAMES_ITERATIONS", "200000"))
    sample_count = int(os.environ.get("MELIX_TOOL_REGISTRY_NAMES_SAMPLES", "5"))
    print(json.dumps(_measure(iterations, sample_count), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
