#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

REPO_ROOT = Path(os.environ.get("MELIX_DATASET_SPLIT_MATCH_PROBE_REPO_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, os.fspath(REPO_ROOT))
sys.path.insert(0, os.fspath(REPO_ROOT / "services/mlx-worker-python"))

import worker.dataset_registry.catalog as catalog


def _relative_paths(file_count: int) -> tuple[Path, ...]:
    splits = ("train", "validation", "test", "eval")
    suffixes = (".jsonl", ".json", ".csv", ".parquet", ".arrow")
    return tuple(
        Path(f"config-{index % 24:02d}")
        / f"{splits[index % len(splits)]}-{index:05d}-of-{file_count:05d}{suffixes[index % len(suffixes)]}"
        for index in range(file_count)
    )


def run_probe(*, file_count: int = 20000, samples: int = 5) -> dict[str, Any]:
    relative_paths = _relative_paths(file_count)
    expected_matches = sum(1 for path in relative_paths if path.name.startswith("validation-"))
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    constructor_call_samples: list[float] = []
    match_samples: list[float] = []
    real_path = Path
    original_catalog_path = catalog.Path

    class CountingPath:
        def __new__(cls, *args: object, **kwargs: object) -> Path:
            nonlocal constructor_calls
            constructor_calls += 1
            return real_path(*args, **kwargs)

    for _ in range(samples):
        constructor_calls = 0
        catalog.Path = CountingPath  # type: ignore[assignment]
        try:
            tracemalloc.start()
            started = time.perf_counter()
            matches = [
                path
                for path in relative_paths
                if catalog._path_matches_split(path, "validation")
            ]
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            _current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        finally:
            catalog.Path = original_catalog_path
            if tracemalloc.is_tracing():  # pragma: no cover - defensive cleanup after interrupted tracing
                tracemalloc.stop()

        if len(matches) != expected_matches:  # pragma: no cover - probe guard rail
            raise SystemExit(f"unexpected split match count: {len(matches)} != {expected_matches}")
        elapsed_samples.append(elapsed_ms)
        peak_samples.append(float(peak))
        constructor_call_samples.append(float(constructor_calls))
        match_samples.append(float(len(matches)))

    return {
        "elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "peak_bytes_mean": statistics.fmean(peak_samples),
        "path_constructor_calls_mean": statistics.fmean(constructor_call_samples),
        "matched_files_mean": statistics.fmean(match_samples),
        "file_count": float(file_count),
        "sample_count": float(samples),
    }


def main() -> int:
    file_count = int(os.environ.get("MELIX_DATASET_SPLIT_MATCH_PROBE_FILE_COUNT", "20000"))
    samples = int(os.environ.get("MELIX_DATASET_SPLIT_MATCH_PROBE_SAMPLES", "5"))
    print(json.dumps(run_probe(file_count=file_count, samples=samples), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
