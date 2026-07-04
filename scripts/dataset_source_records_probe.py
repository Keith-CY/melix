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

_SOURCE_KIND_SUFFIXES = (
    (".txt", "text"),
    (".md", "markdown"),
    (".py", "code"),
    (".jsonl", "structured_data"),
    (".json", "structured_data"),
    (".csv", "structured_data"),
    (".tsv", "structured_data"),
)


def _build_tree(root: Path, *, directory_count: int, files_per_directory: int) -> int:
    total = 0
    suffixes = _SOURCE_KIND_SUFFIXES
    for directory_index in range(directory_count):
        directory = root / f"group-{directory_index:04d}"
        directory.mkdir(parents=True, exist_ok=True)
        for file_index in range(files_per_directory):
            suffix, _source_kind = suffixes[file_index % len(suffixes)]
            (directory / f"sample-{directory_index:04d}-{file_index:04d}{suffix}").write_text(
                "Melix source row\n",
                encoding="utf-8",
            )
            total += 1
    return total


def _expected_source_kinds(file_count: int) -> list[str]:
    suffixes = _SOURCE_KIND_SUFFIXES
    return [suffixes[file_index % len(suffixes)][1] for file_index in range(file_count)]


def _expected_source_kind_tree(*, directory_count: int, files_per_directory: int) -> list[str]:
    expected_directory_kinds = _expected_source_kinds(files_per_directory)
    return expected_directory_kinds * directory_count


def _iter_source_file_paths(input_path: Path) -> list[Path]:
    helper = getattr(dataset_preparation, "_iter_source_file_paths", None)
    if helper is None:
        return sorted(path for path in input_path.rglob("*") if path.is_file())
    return helper(input_path)


def measure(*, directory_count: int, files_per_directory: int, samples: int) -> dict[str, float]:
    elapsed_ms: list[float] = []
    source_kind_elapsed_ms: list[float] = []
    record_elapsed_ms: list[float] = []
    file_counts: list[float] = []
    with tempfile.TemporaryDirectory(prefix="melix-dataset-source-records-probe-") as tmp:
        root = Path(tmp) / "raw-inputs"
        expected_count = _build_tree(root, directory_count=directory_count, files_per_directory=files_per_directory)
        expected_first = root / "group-0000" / "sample-0000-0000.txt"
        last_suffix, _last_kind = _SOURCE_KIND_SUFFIXES[(files_per_directory - 1) % len(_SOURCE_KIND_SUFFIXES)]
        expected_last = (
            root
            / f"group-{directory_count - 1:04d}"
            / f"sample-{directory_count - 1:04d}-{files_per_directory - 1:04d}{last_suffix}"
        )
        expected_kinds = _expected_source_kind_tree(
            directory_count=directory_count,
            files_per_directory=files_per_directory,
        )
        for _ in range(samples):
            started = time.perf_counter()
            paths = _iter_source_file_paths(root)
            elapsed_ms.append((time.perf_counter() - started) * 1000.0)
            file_counts.append(float(len(paths)))
            if len(paths) != expected_count:
                raise RuntimeError(f"unexpected source file count: {len(paths)} != {expected_count}")
            if paths[0] != expected_first or paths[-1] != expected_last:
                raise RuntimeError("source file ordering changed")
            cache = getattr(dataset_preparation, "_SOURCE_KIND_BY_NAME", None)
            clear_cache = getattr(cache, "clear", None)
            if clear_cache is not None:
                clear_cache()
            started = time.perf_counter()
            source_kinds = [dataset_preparation._source_kind(path) for path in paths]
            source_kind_elapsed_ms.append((time.perf_counter() - started) * 1000.0)
            if source_kinds != expected_kinds:
                raise RuntimeError("source kind classification changed")
            started = time.perf_counter()
            records = [
                dataset_preparation._record(
                    path=path,
                    source_kind=source_kind,
                    text="Melix source row\n",
                    metadata={},
                )
                for path, source_kind in zip(paths, source_kinds)
            ]
            record_elapsed_ms.append((time.perf_counter() - started) * 1000.0)
            if records[0]["byte_size"] != len("Melix source row\n".encode("utf-8")):
                raise RuntimeError("source record byte accounting changed")
    return {
        "elapsed_ms_mean": statistics.fmean(elapsed_ms),
        "elapsed_ms_min": min(elapsed_ms),
        "elapsed_ms_p95": sorted(elapsed_ms)[int((len(elapsed_ms) - 1) * 0.95)],
        "source_kind_elapsed_ms_mean": statistics.fmean(source_kind_elapsed_ms),
        "source_kind_elapsed_ms_min": min(source_kind_elapsed_ms),
        "source_kind_elapsed_ms_p95": sorted(source_kind_elapsed_ms)[int((len(source_kind_elapsed_ms) - 1) * 0.95)],
        "record_elapsed_ms_mean": statistics.fmean(record_elapsed_ms),
        "record_elapsed_ms_min": min(record_elapsed_ms),
        "record_elapsed_ms_p95": sorted(record_elapsed_ms)[int((len(record_elapsed_ms) - 1) * 0.95)],
        "directory_count": float(directory_count),
        "files_per_directory": float(files_per_directory),
        "file_count_mean": statistics.fmean(file_counts),
        "source_kind_variant_count": float(len(_SOURCE_KIND_SUFFIXES)),
        "sample_count": float(samples),
    }


def main() -> int:
    directory_count = int(os.environ.get("MELIX_DATASET_SOURCE_RECORDS_PROBE_DIRS", "250"))
    files_per_directory = int(os.environ.get("MELIX_DATASET_SOURCE_RECORDS_PROBE_FILES_PER_DIR", "28"))
    samples = int(os.environ.get("MELIX_DATASET_SOURCE_RECORDS_PROBE_SAMPLES", "11"))
    print(json.dumps(measure(directory_count=directory_count, files_per_directory=files_per_directory, samples=samples), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
