#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(os.environ.get("MELIX_DATASET_SOURCE_RECORDS_REPO_ROOT", Path.cwd()))
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.productization import dataset_preparation  # noqa: E402


def _build_tree(root: Path, *, directory_count: int, files_per_directory: int) -> int:
    total = 0
    for directory_index in range(directory_count):
        directory = root / f"group-{directory_index:04d}"
        directory.mkdir(parents=True, exist_ok=True)
        for file_index in range(files_per_directory):
            (directory / f"sample-{file_index:04d}.txt").write_text("Melix source row\n", encoding="utf-8")
            total += 1
    return total


def _iter_source_file_paths(input_path: Path) -> list[Path]:
    helper = getattr(dataset_preparation, "_iter_source_file_paths", None)
    if helper is None:
        return sorted(path for path in input_path.rglob("*") if path.is_file())
    return helper(input_path)


def measure(*, directory_count: int, files_per_directory: int, samples: int) -> dict[str, float]:
    elapsed_ms: list[float] = []
    source_kind_elapsed_ms: list[float] = []
    file_counts: list[float] = []
    with tempfile.TemporaryDirectory(prefix="melix-dataset-source-records-probe-") as tmp:
        root = Path(tmp) / "raw-inputs"
        expected_count = _build_tree(root, directory_count=directory_count, files_per_directory=files_per_directory)
        expected_first = root / "group-0000" / "sample-0000.txt"
        expected_last = root / f"group-{directory_count - 1:04d}" / f"sample-{files_per_directory - 1:04d}.txt"
        for _ in range(samples):
            started = time.perf_counter()
            paths = _iter_source_file_paths(root)
            elapsed_ms.append((time.perf_counter() - started) * 1000.0)
            file_counts.append(float(len(paths)))
            if len(paths) != expected_count:
                raise RuntimeError(f"unexpected source file count: {len(paths)} != {expected_count}")
            if paths[0] != expected_first or paths[-1] != expected_last:
                raise RuntimeError("source file ordering changed")
            started = time.perf_counter()
            source_kinds = [dataset_preparation._source_kind(path) for path in paths]
            source_kind_elapsed_ms.append((time.perf_counter() - started) * 1000.0)
            if any(source_kind != "text" for source_kind in source_kinds):
                raise RuntimeError("source kind classification changed")
    return {
        "elapsed_ms_mean": statistics.fmean(elapsed_ms),
        "elapsed_ms_min": min(elapsed_ms),
        "elapsed_ms_p95": sorted(elapsed_ms)[int((len(elapsed_ms) - 1) * 0.95)],
        "source_kind_elapsed_ms_mean": statistics.fmean(source_kind_elapsed_ms),
        "source_kind_elapsed_ms_min": min(source_kind_elapsed_ms),
        "source_kind_elapsed_ms_p95": sorted(source_kind_elapsed_ms)[int((len(source_kind_elapsed_ms) - 1) * 0.95)],
        "directory_count": float(directory_count),
        "files_per_directory": float(files_per_directory),
        "file_count_mean": statistics.fmean(file_counts),
        "sample_count": float(samples),
    }


def main() -> int:
    directory_count = int(os.environ.get("MELIX_DATASET_SOURCE_RECORDS_PROBE_DIRS", "250"))
    files_per_directory = int(os.environ.get("MELIX_DATASET_SOURCE_RECORDS_PROBE_FILES_PER_DIR", "24"))
    samples = int(os.environ.get("MELIX_DATASET_SOURCE_RECORDS_PROBE_SAMPLES", "7"))
    print(json.dumps(measure(directory_count=directory_count, files_per_directory=files_per_directory, samples=samples), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
