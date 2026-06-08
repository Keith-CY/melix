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

REPO_ROOT = Path(os.environ.get("MELIX_DATASET_PREVIEW_PROBE_REPO_ROOT") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.dataset_registry.catalog import read_hf_dataset_snapshot_rows


def _int_env(name: str, default: int) -> int:
    raw_value = os.environ.get(name, "")
    if not raw_value:
        return default
    return int(raw_value)


def _build_snapshot(root: Path, *, row_count: int, sidecar_count: int) -> Path:
    snapshot_root = root / "snapshot"
    snapshot_root.mkdir(parents=True)
    for index in range(sidecar_count, 0, -1):
        (snapshot_root / f"000-sidecar-{index:05d}.txt").write_text("ignored\n", encoding="utf-8")
    snapshot_dir = snapshot_root / "data"
    snapshot_dir.mkdir()
    rows = [{"prompt": f"prompt-{index}", "answer": f"answer-{index}"} for index in range(row_count)]
    (snapshot_dir / "train.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")
    (snapshot_root / "README.md").write_text("# Synthetic dataset\n", encoding="utf-8")
    return snapshot_root


def main() -> int:
    row_count = _int_env("MELIX_DATASET_PREVIEW_PROBE_FILES", 50_000)
    sidecar_count = _int_env("MELIX_DATASET_PREVIEW_PROBE_SIDECARS", 1_000)
    sample_count = _int_env("MELIX_DATASET_PREVIEW_PROBE_SAMPLES", 7)
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    with tempfile.TemporaryDirectory(prefix="melix-dataset-preview-probe-") as temp_dir:
        snapshot_dir = _build_snapshot(
            Path(temp_dir), row_count=row_count, sidecar_count=sidecar_count
        )
        expected = [{"prompt": "prompt-0", "answer": "answer-0"}]
        zero_limit_elapsed_samples: list[float] = []
        zero_limit_peak_samples: list[float] = []
        for _ in range(sample_count):
            tracemalloc.start()
            started = time.perf_counter()
            rows = read_hf_dataset_snapshot_rows(snapshot_dir, limit=1)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            _, peak_bytes = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            if rows != expected:
                raise RuntimeError(f"unexpected preview rows: {rows!r}")
            elapsed_samples.append(elapsed_ms)
            peak_samples.append(float(peak_bytes))

            tracemalloc.start()
            started = time.perf_counter()
            zero_limit_rows = read_hf_dataset_snapshot_rows(snapshot_dir, limit=0)
            zero_limit_elapsed_ms = (time.perf_counter() - started) * 1000.0
            _, zero_limit_peak_bytes = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            if zero_limit_rows != []:  # pragma: no cover
                raise RuntimeError(f"unexpected zero-limit rows: {zero_limit_rows!r}")
            zero_limit_elapsed_samples.append(zero_limit_elapsed_ms)
            zero_limit_peak_samples.append(float(zero_limit_peak_bytes))
    print(
        json.dumps(
            {
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "elapsed_ms_min": round(min(elapsed_samples), 6),
                "peak_bytes_mean": round(statistics.fmean(peak_samples), 3),
                "zero_limit_elapsed_ms_mean": round(statistics.fmean(zero_limit_elapsed_samples), 6),
                "zero_limit_peak_bytes_mean": round(statistics.fmean(zero_limit_peak_samples), 3),
                "file_count": float(row_count),
                "sidecar_count": float(sidecar_count),
                "rows_returned": 1.0,
                "zero_limit_rows_returned": 0.0,
                "sample_count": float(sample_count),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
