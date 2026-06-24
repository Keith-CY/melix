#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
import tracemalloc


ROOT = Path(__file__).resolve().parents[1]
WORKER_ROOT = ROOT / "services/mlx-worker-python"
for candidate in (ROOT, WORKER_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))  # pragma: no cover - script bootstrap

from worker.productization.export_target_smoke import build_smoke_metrics_report


FIXTURE_ROOT = (
    ROOT
    / "services/mlx-worker-python/fixtures/runtime-export/target-manifests.dev.v1"
)


def _env_int(name: str, default: int, minimum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, value)


def main() -> int:
    manifests = sorted(FIXTURE_ROOT.glob("*/export-target-manifest.json"))
    iterations = _env_int("MELIX_RUNTIME_EXPORT_SMOKE_PROBE_ITERATIONS", 30, 1)
    samples = _env_int("MELIX_RUNTIME_EXPORT_SMOKE_PROBE_SAMPLES", 5, 1)
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    target_count = 0.0
    metadata_latency_ms = 0.0
    load_latency_ms = 0.0
    generation_latency_ms = 0.0
    preview_bytes = 0.0
    timeout_count = 0.0
    waiver_count = 0.0

    for _sample in range(samples):
        tracemalloc.start()
        try:
            started = time.perf_counter()
            for _index in range(iterations):
                with tempfile.TemporaryDirectory(prefix="melix-export-smoke-probe-") as directory:
                    report = build_smoke_metrics_report(manifests, Path(directory))
                if report.get("ok") is not True:
                    raise SystemExit("export smoke policy probe failed")
                target_count = float(report["target_count"])
                metadata_latency_ms = float(report["metadata_check_latency_ms"])
                load_latency_ms = float(report["load_smoke_latency_ms"])
                generation_latency_ms = float(report["generation_smoke_latency_ms"])
                preview_bytes = float(report["output_preview_byte_count"])
                timeout_count = float(report["timeout_count"])
                waiver_count = float(report["waiver_count"])
            elapsed_samples.append((time.perf_counter() - started) * 1000.0)
            _, peak_bytes = tracemalloc.get_traced_memory()
            peak_samples.append(float(peak_bytes))
        finally:
            tracemalloc.stop()

    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(elapsed_samples),
                "peak_bytes_mean": statistics.fmean(peak_samples),
                "target_count": target_count,
                "metadata_check_latency_ms": metadata_latency_ms,
                "load_smoke_latency_ms": load_latency_ms,
                "generation_smoke_latency_ms": generation_latency_ms,
                "output_preview_byte_count": preview_bytes,
                "timeout_count": timeout_count,
                "waiver_count": waiver_count,
                "iteration_count": float(iterations),
                "sample_count": float(samples),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI guard
    raise SystemExit(main())
