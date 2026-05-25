#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(os.environ.get("MELIX_TRAJECTORY_MANIFEST_JSON_REPO_ROOT", Path.cwd()))
WORKER_ROOT = REPO_ROOT / "services" / "mlx-worker-python"
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from worker.trajectory_provenance import (  # noqa: E402
    load_trajectory_provenance_from_snapshot_manifest,
)


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _manifest_payload(component_count: int) -> dict[str, Any]:
    return {
        "format": "agentic_tool_trace",
        "source_dataset_id": "agentic-snapshot",
        "version": "2026-05-25",
        "trajectory_schema_version": "melix.agentic_tool_trace.v1",
        "trajectory_split": "train",
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


def _baseline_load(manifest_path: Path) -> dict[str, Any]:
    payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    # Import lazily so this script can execute against base checkouts that do not
    # contain any helper refactors from the head checkout.
    from worker.trajectory_provenance import trajectory_provenance_from_snapshot_manifest

    return trajectory_provenance_from_snapshot_manifest(
        payload,
        snapshot_manifest_path=manifest_path,
    )


def _measure(func: Callable[[Path], dict[str, Any]], manifest_path: Path, iterations: int) -> tuple[float, int]:
    tracemalloc.start()
    start = time.perf_counter()
    checksum = 0
    for _ in range(iterations):
        provenance = func(manifest_path)
        checksum += int(provenance["trajectory_quality_metrics"]["reward_coverage_count"])
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    expected = iterations * int(_manifest_payload(1)["trajectory_quality_metrics"]["reward_coverage_count"])
    if checksum <= 0 or checksum % expected != 0:
        raise RuntimeError("probe checksum mismatch")
    return elapsed_ms, peak_bytes


def _mean(values: list[float]) -> float:
    return float(statistics.fmean(values)) if values else 0.0


def run_probe() -> dict[str, float]:
    iterations = _int_env("MELIX_TRAJECTORY_MANIFEST_JSON_PROBE_ITERATIONS", 2000)
    samples = _int_env("MELIX_TRAJECTORY_MANIFEST_JSON_PROBE_SAMPLES", 5)
    component_count = _int_env("MELIX_TRAJECTORY_MANIFEST_JSON_PROBE_COMPONENTS", 64)

    with tempfile.TemporaryDirectory(prefix="melix-trajectory-manifest-json-") as tmp:
        manifest_path = Path(tmp) / "manifest.json"
        manifest_path.write_bytes(
            (json.dumps(_manifest_payload(component_count), separators=(",", ":")) + "\n").encode("utf-8")
        )

        baseline_ms: list[float] = []
        optimized_ms: list[float] = []
        baseline_peak: list[float] = []
        optimized_peak: list[float] = []
        for _ in range(samples):
            elapsed, peak = _measure(_baseline_load, manifest_path, iterations)
            baseline_ms.append(elapsed)
            baseline_peak.append(float(peak))
            elapsed, peak = _measure(
                load_trajectory_provenance_from_snapshot_manifest,
                manifest_path,
                iterations,
            )
            optimized_ms.append(elapsed)
            optimized_peak.append(float(peak))

    old_mean = _mean(baseline_ms)
    new_mean = _mean(optimized_ms)
    return {
        "old_mean_ms": old_mean,
        "new_mean_ms": new_mean,
        "elapsed_ms_mean": new_mean,
        "delta_ms": new_mean - old_mean,
        "speedup": old_mean / new_mean if new_mean > 0 else 0.0,
        "old_peak_bytes_mean": _mean(baseline_peak),
        "new_peak_bytes_mean": _mean(optimized_peak),
        "peak_bytes_mean": _mean(optimized_peak),
        "sample_count": float(samples),
        "iteration_count": float(iterations),
        "component_count": float(component_count),
    }


def main() -> int:
    print(json.dumps(run_probe(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
