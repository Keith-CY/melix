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


def _repo_root() -> Path:
    override = os.environ.get("MELIX_DATASET_SELECTED_SPLIT_REPO_ROOT", "")
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parents[1]


REPO_ROOT = _repo_root()
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

import worker.dataset_registry.catalog as catalog
from worker.dataset_registry.catalog import read_hf_dataset_snapshot_rows


def _int_env(name: str, default: int) -> int:
    raw_value = os.environ.get(name, "")
    if not raw_value:
        return default
    return int(raw_value)


def _build_snapshot(root: Path, *, file_count: int) -> Path:
    snapshot_dir = root / "snapshot"
    data_dir = snapshot_dir / "data"
    data_dir.mkdir(parents=True)
    (snapshot_dir / "README.md").write_text("# Synthetic dataset\n", encoding="utf-8")
    splits = ("train", "validation", "test")
    for index in range(file_count):
        split = splits[index % len(splits)]
        (data_dir / f"{split}-{index:05d}.jsonl").write_text(
            json.dumps({"prompt": f"{split}-{index}", "answer": f"answer-{index}"}) + "\n",
            encoding="utf-8",
        )
    return snapshot_dir


def main() -> int:
    file_count = _int_env("MELIX_DATASET_SELECTED_SPLIT_PROBE_FILES", 1500)
    sample_count = _int_env("MELIX_DATASET_SELECTED_SPLIT_PROBE_SAMPLES", 7)
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    read_file_samples: list[float] = []
    with tempfile.TemporaryDirectory(prefix="melix-dataset-selected-split-probe-") as temp_dir:
        snapshot_dir = _build_snapshot(Path(temp_dir), file_count=file_count)
        expected = [{"prompt": "validation-1", "answer": "answer-1"}]
        original_reader = catalog._read_rows_from_file

        for _ in range(sample_count):
            read_files: list[Path] = []

            def tracking_reader(path: Path, *, limit: int | None = None) -> list[dict[str, object]]:
                read_files.append(path)
                return original_reader(path, limit=limit)

            catalog._read_rows_from_file = tracking_reader
            try:
                tracemalloc.start()
                started = time.perf_counter()
                rows = read_hf_dataset_snapshot_rows(snapshot_dir, split="validation", limit=1)
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                _, peak_bytes = tracemalloc.get_traced_memory()
                tracemalloc.stop()
            finally:
                catalog._read_rows_from_file = original_reader
                if tracemalloc.is_tracing():
                    tracemalloc.stop()
            if rows != expected:
                raise RuntimeError(f"unexpected selected split rows: {rows!r}")
            if len(read_files) != 1 or read_files[0].name != "validation-00001.jsonl":
                raise RuntimeError(f"unexpected selected split file reads: {read_files!r}")
            elapsed_samples.append(elapsed_ms)
            peak_samples.append(float(peak_bytes))
            read_file_samples.append(float(len(read_files)))
    print(
        json.dumps(
            {
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "elapsed_ms_min": round(min(elapsed_samples), 6),
                "peak_bytes_mean": round(statistics.fmean(peak_samples), 3),
                "file_read_calls_mean": round(statistics.fmean(read_file_samples), 3),
                "file_count": float(file_count),
                "rows_returned": 1.0,
                "sample_count": float(sample_count),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
