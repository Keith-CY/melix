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

import worker.dataset_registry.catalog as catalog


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
    for index in range(row_count):
        (snapshot_dir / f"part-{index:05d}.jsonl").write_text(
            json.dumps({"prompt": f"prompt-{index}", "answer": f"answer-{index}"}) + "\n",
            encoding="utf-8",
        )
    (snapshot_root / "README.md").write_text("# Synthetic dataset\n", encoding="utf-8")
    return snapshot_root


def _read_rows_with_yield_count(snapshot_dir: Path, *, limit: int) -> tuple[list[dict[str, object]], int]:
    original_iter = catalog._iter_supported_dataset_files
    yielded_paths: set[Path] = set()

    def tracked_iter(path: Path):
        for candidate in original_iter(path):
            yielded_paths.add(candidate)
            yield candidate

    catalog._iter_supported_dataset_files = tracked_iter
    try:
        rows = catalog.read_hf_dataset_snapshot_rows(snapshot_dir, limit=limit)
    finally:
        catalog._iter_supported_dataset_files = original_iter
    return rows, len(yielded_paths)


def main() -> int:
    row_count = _int_env("MELIX_DATASET_PREVIEW_PROBE_FILES", 50_000)
    sidecar_count = _int_env("MELIX_DATASET_PREVIEW_PROBE_SIDECARS", 1_000)
    sample_count = _int_env("MELIX_DATASET_PREVIEW_PROBE_SAMPLES", 7)
    multi_limit = min(_int_env("MELIX_DATASET_PREVIEW_PROBE_MULTI_LIMIT", 5), row_count)
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    multi_limit_elapsed_samples: list[float] = []
    multi_limit_peak_samples: list[float] = []
    multi_limit_yielded_samples: list[float] = []
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
            rows = catalog.read_hf_dataset_snapshot_rows(snapshot_dir, limit=1)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            _, peak_bytes = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            if rows != expected:
                raise RuntimeError(f"unexpected preview rows: {rows!r}")
            elapsed_samples.append(elapsed_ms)
            peak_samples.append(float(peak_bytes))

            tracemalloc.start()
            started = time.perf_counter()
            zero_limit_rows = catalog.read_hf_dataset_snapshot_rows(snapshot_dir, limit=0)
            zero_limit_elapsed_ms = (time.perf_counter() - started) * 1000.0
            _, zero_limit_peak_bytes = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            if zero_limit_rows != []:  # pragma: no cover
                raise RuntimeError(f"unexpected zero-limit rows: {zero_limit_rows!r}")
            zero_limit_elapsed_samples.append(zero_limit_elapsed_ms)
            zero_limit_peak_samples.append(float(zero_limit_peak_bytes))

            tracemalloc.start()
            started = time.perf_counter()
            multi_limit_rows, multi_limit_yielded = _read_rows_with_yield_count(
                snapshot_dir, limit=multi_limit
            )
            multi_limit_elapsed_ms = (time.perf_counter() - started) * 1000.0
            _, multi_limit_peak_bytes = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            if len(multi_limit_rows) != multi_limit:  # pragma: no cover
                raise RuntimeError(f"unexpected multi-limit rows: {multi_limit_rows!r}")
            multi_limit_elapsed_samples.append(multi_limit_elapsed_ms)
            multi_limit_peak_samples.append(float(multi_limit_peak_bytes))
            multi_limit_yielded_samples.append(float(multi_limit_yielded))
    print(
        json.dumps(
            {
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "elapsed_ms_min": round(min(elapsed_samples), 6),
                "peak_bytes_mean": round(statistics.fmean(peak_samples), 3),
                "zero_limit_elapsed_ms_mean": round(statistics.fmean(zero_limit_elapsed_samples), 6),
                "zero_limit_peak_bytes_mean": round(statistics.fmean(zero_limit_peak_samples), 3),
                "multi_limit_elapsed_ms_mean": round(statistics.fmean(multi_limit_elapsed_samples), 6),
                "multi_limit_peak_bytes_mean": round(statistics.fmean(multi_limit_peak_samples), 3),
                "multi_limit_dataset_files_yielded_mean": round(
                    statistics.fmean(multi_limit_yielded_samples), 3
                ),
                "multi_limit": float(multi_limit),
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
