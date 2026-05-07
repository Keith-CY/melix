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
from typing import Any

REPO_ROOT = Path(os.environ.get("MELIX_DATASET_JSON_LIMIT_PROBE_REPO_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, os.fspath(REPO_ROOT))
sys.path.insert(0, os.fspath(REPO_ROOT / "services/mlx-worker-python"))

import worker.dataset_registry.catalog as catalog


def _write_rows(path: Path, row_count: int) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write("[\n")
        for index in range(row_count):
            if index:
                handle.write(",\n")
            handle.write(json.dumps({"prompt": f"prompt-{index}", "answer": f"answer-{index}"}))
        handle.write("\n]")


def run_probe(*, row_count: int = 50000, limit: int = 1, samples: int = 5) -> dict[str, Any]:
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    read_text_samples: list[float] = []
    row_samples: list[float] = []

    with tempfile.TemporaryDirectory(prefix="melix-dataset-json-limit-probe-") as temp_dir:
        snapshot_dir = Path(temp_dir) / "snapshot"
        data_dir = snapshot_dir / "data"
        data_dir.mkdir(parents=True)
        rows_path = data_dir / "train.json"
        _write_rows(rows_path, row_count)
        file_bytes = float(rows_path.stat().st_size)
        original_read_text = Path.read_text

        def counting_read_text(self: Path, *args: object, **kwargs: object) -> str:
            nonlocal read_text_calls
            if self == rows_path:
                read_text_calls += 1
            return original_read_text(self, *args, **kwargs)

        for _ in range(samples):
            read_text_calls = 0
            Path.read_text = counting_read_text  # type: ignore[method-assign]
            try:
                tracemalloc.start()
                started = time.perf_counter()
                rows = catalog.read_hf_dataset_snapshot_rows(snapshot_dir, split="train", limit=limit)
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                _current, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
            finally:
                Path.read_text = original_read_text  # type: ignore[method-assign]
                if tracemalloc.is_tracing():  # pragma: no cover - defensive cleanup
                    tracemalloc.stop()

            if rows != [{"prompt": "prompt-0", "answer": "answer-0"}]:  # pragma: no cover - probe guard rail
                raise SystemExit(f"unexpected limited rows: {rows!r}")
            elapsed_samples.append(elapsed_ms)
            peak_samples.append(float(peak))
            read_text_samples.append(float(read_text_calls))
            row_samples.append(float(len(rows)))

    return {
        "json_limit_elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "json_limit_peak_bytes_mean": statistics.fmean(peak_samples),
        "json_limit_read_text_calls_mean": statistics.fmean(read_text_samples),
        "json_limit_rows_mean": statistics.fmean(row_samples),
        "json_file_bytes": file_bytes,
        "json_row_count": float(row_count),
        "json_limit": float(limit),
        "sample_count": float(samples),
    }


def main() -> int:
    row_count = int(os.environ.get("MELIX_DATASET_JSON_LIMIT_PROBE_ROW_COUNT", "50000"))
    limit = int(os.environ.get("MELIX_DATASET_JSON_LIMIT_PROBE_LIMIT", "1"))
    samples = int(os.environ.get("MELIX_DATASET_JSON_LIMIT_PROBE_SAMPLES", "5"))
    print(json.dumps(run_probe(row_count=row_count, limit=limit, samples=samples), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
