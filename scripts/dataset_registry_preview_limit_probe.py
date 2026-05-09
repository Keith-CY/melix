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


def _build_snapshot(root: Path, *, row_count: int) -> Path:
    snapshot_dir = root / "snapshot" / "data"
    snapshot_dir.mkdir(parents=True)
    rows = [{"prompt": f"prompt-{index}", "answer": f"answer-{index}"} for index in range(row_count)]
    (snapshot_dir / "train.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")
    (root / "snapshot" / "README.md").write_text("# Synthetic dataset\n", encoding="utf-8")
    return root / "snapshot"


def main() -> int:
    row_count = _int_env("MELIX_DATASET_PREVIEW_PROBE_FILES", 50_000)
    sample_count = _int_env("MELIX_DATASET_PREVIEW_PROBE_SAMPLES", 7)
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    with tempfile.TemporaryDirectory(prefix="melix-dataset-preview-probe-") as temp_dir:
        snapshot_dir = _build_snapshot(Path(temp_dir), row_count=row_count)
        expected = [{"prompt": "prompt-0", "answer": "answer-0"}]
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
    print(
        json.dumps(
            {
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "elapsed_ms_min": round(min(elapsed_samples), 6),
                "peak_bytes_mean": round(statistics.fmean(peak_samples), 3),
                "file_count": float(row_count),
                "rows_returned": 1.0,
                "sample_count": float(sample_count),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
