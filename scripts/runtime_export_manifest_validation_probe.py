#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import statistics
import sys
import time
import tracemalloc


ROOT = Path(__file__).resolve().parents[1]
WORKER_ROOT = ROOT / "services/mlx-worker-python"
for candidate in (ROOT, WORKER_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))  # pragma: no cover - script bootstrap

from worker.productization.export_target_manifest import validate_export_target_manifest_file


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
    iterations = _env_int("MELIX_RUNTIME_EXPORT_MANIFEST_PROBE_ITERATIONS", 250, 1)
    samples = _env_int("MELIX_RUNTIME_EXPORT_MANIFEST_PROBE_SAMPLES", 5, 1)
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    schema_errors = 0
    manifest_bytes = sum(path.stat().st_size for path in manifests)

    for _ in range(samples):
        tracemalloc.start()
        started = time.perf_counter()
        for _index in range(iterations):
            for path in manifests:
                report = validate_export_target_manifest_file(
                    path,
                    fixture_count=len(manifests),
                )
                schema_errors += report.schema_error_count
                if not report.ok:
                    raise SystemExit(f"export target manifest fixture failed validation: {path}")
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_samples.append(float(peak_bytes))

    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(elapsed_samples),
                "peak_bytes_mean": statistics.fmean(peak_samples),
                "fixture_count": float(len(manifests)),
                "schema_error_count": float(schema_errors),
                "manifest_byte_size": float(manifest_bytes),
                "iteration_count": float(iterations),
                "sample_count": float(samples),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI guard
    raise SystemExit(main())
