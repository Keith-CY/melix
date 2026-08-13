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

from worker.productization.export_target_layout import build_layout_metrics_report


FIXTURE_ROOT = (
    ROOT
    / "services/mlx-worker-python/fixtures/runtime-export/target-manifests.dev.v1"
)


def _fixture_manifest_paths() -> list[Path]:
    paths: list[Path] = []
    try:
        entries = os.scandir(FIXTURE_ROOT)
    except FileNotFoundError:
        return paths
    with entries:
        for entry in entries:
            if not entry.is_dir(follow_symlinks=False):
                continue
            manifest_path = Path(entry.path) / "export-target-manifest.json"
            if manifest_path.is_file():
                paths.append(manifest_path)
    paths.sort()
    return paths


def _env_int(name: str, default: int, minimum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, value)


def main() -> int:
    manifests = _fixture_manifest_paths()
    iterations = _env_int("MELIX_RUNTIME_EXPORT_LAYOUT_PROBE_ITERATIONS", 40, 1)
    samples = _env_int("MELIX_RUNTIME_EXPORT_LAYOUT_PROBE_SAMPLES", 5, 1)
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    target_count = 0.0
    retained_bytes = 0.0
    cleanable_bytes = 0.0
    deleted_files = 0.0
    decision_count = 0.0

    for _sample in range(samples):
        tracemalloc.start()
        started = time.perf_counter()
        for _index in range(iterations):
            with tempfile.TemporaryDirectory(prefix="melix-export-layout-probe-") as directory:
                report = build_layout_metrics_report(
                    manifests,
                    Path(directory),
                    cleanup="dry-run",
                    create_placeholder_files=True,
                )
            if report.get("ok") is not True:
                raise SystemExit("export layout retention probe failed")
            target_count = float(report["target_count"])
            retained_bytes = float(report["retained_byte_size"])
            cleanable_bytes = float(report["cleanable_byte_size"])
            deleted_files = float(report["deleted_file_count"])
            decision_count = float(report["retention_decision_count"])
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_samples.append(float(peak_bytes))

    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(elapsed_samples),
                "peak_bytes_mean": statistics.fmean(peak_samples),
                "target_count": target_count,
                "retained_byte_size": retained_bytes,
                "cleanable_byte_size": cleanable_bytes,
                "deleted_file_count": deleted_files,
                "retention_decision_count": decision_count,
                "iteration_count": float(iterations),
                "sample_count": float(samples),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI guard
    raise SystemExit(main())
