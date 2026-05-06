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

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

import worker.dataset_registry.catalog as catalog


def _build_snapshot(snapshot_dir: Path, *, group_count: int, files_per_group: int) -> None:
    for group_index in range(group_count):
        group_dir = snapshot_dir / f"group-{group_index:04d}"
        group_dir.mkdir(parents=True, exist_ok=True)
        for file_index in range(files_per_group):
            path = group_dir / f"train-{file_index:04d}.jsonl"
            path.write_text(json.dumps({"prompt": f"{group_index}-{file_index}"}) + "\n", encoding="utf-8")
    (snapshot_dir / "README.md").write_text("# synthetic dataset\n", encoding="utf-8")


def _sample(snapshot_dir: Path, *, limit: int) -> dict[str, float]:
    original_iter = catalog._iter_supported_dataset_files
    yielded_paths: set[Path] = set()

    def tracked_iter(path: Path):
        for candidate in original_iter(path):
            yielded_paths.add(candidate)
            yield candidate

    catalog._iter_supported_dataset_files = tracked_iter
    try:
        tracemalloc.start()
        started = time.perf_counter()
        rows = catalog.read_hf_dataset_snapshot_rows(snapshot_dir, limit=limit)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    finally:
        catalog._iter_supported_dataset_files = original_iter
    if len(rows) != limit:
        raise SystemExit(f"expected {limit} rows, got {len(rows)}")
    return {
        "elapsed_ms": elapsed_ms,
        "peak_bytes": float(peak_bytes),
        "dataset_files_yielded": float(len(yielded_paths)),
    }


def main() -> int:
    group_count = int(os.environ.get("MELIX_DATASET_LIMIT_PROBE_GROUPS", "160"))
    files_per_group = int(os.environ.get("MELIX_DATASET_LIMIT_PROBE_FILES_PER_GROUP", "8"))
    limit = int(os.environ.get("MELIX_DATASET_LIMIT_PROBE_LIMIT", "5"))
    sample_count = int(os.environ.get("MELIX_DATASET_LIMIT_PROBE_SAMPLES", "5"))
    with tempfile.TemporaryDirectory(prefix="melix-dataset-limit-probe-") as tmp:
        snapshot_dir = Path(tmp) / "snapshot"
        snapshot_dir.mkdir()
        _build_snapshot(snapshot_dir, group_count=group_count, files_per_group=files_per_group)
        samples = [_sample(snapshot_dir, limit=limit) for _ in range(sample_count)]
    metrics = {
        "elapsed_ms_mean": statistics.fmean(sample["elapsed_ms"] for sample in samples),
        "peak_bytes_mean": statistics.fmean(sample["peak_bytes"] for sample in samples),
        "dataset_files_yielded_mean": statistics.fmean(sample["dataset_files_yielded"] for sample in samples),
        "synthetic_file_count": float(group_count * files_per_group),
        "limit": float(limit),
        "sample_count": float(sample_count),
    }
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
