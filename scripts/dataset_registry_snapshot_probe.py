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
from typing import Any

REPO_ROOT = Path(os.environ.get("MELIX_DATASET_REGISTRY_PROBE_REPO_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, os.fspath(REPO_ROOT))
sys.path.insert(0, os.fspath(REPO_ROOT / "services/mlx-worker-python"))

import worker.dataset_registry.catalog as catalog
from worker.dataset_registry.catalog import DatasetCatalog


def _write_probe_snapshot(home: Path, *, file_count: int) -> tuple[Path, int]:
    cache_repo_dir = home / ".cache" / "huggingface" / "hub" / "datasets--org--probe"
    snapshot_dir = cache_repo_dir / "snapshots" / "snapshot-probe"
    refs_dir = cache_repo_dir / "refs"
    refs_dir.mkdir(parents=True)
    refs_dir.joinpath("main").write_text("snapshot-probe", encoding="utf-8")
    expected_files = 0
    splits = ("train", "validation", "test")
    for index in range(file_count):
        config = f"config-{index % 12:02d}"
        split = splits[index % len(splits)]
        data_dir = snapshot_dir / config
        data_dir.mkdir(parents=True, exist_ok=True)
        path = data_dir / f"{split}-{index:05d}.jsonl"
        path.write_text('{"prompt":"hello","answer":"world"}\n', encoding="utf-8")
        expected_files += 1
    snapshot_dir.joinpath("README.md").write_text("# Probe dataset\n", encoding="utf-8")
    expected_files += 1
    return snapshot_dir, expected_files


def run_probe(*, file_count: int = 2400, samples: int = 5) -> dict[str, Any]:
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    helper_call_samples: list[float] = []
    file_count_samples: list[float] = []
    original_split = catalog._inferred_split
    original_config = catalog._inferred_config

    for _ in range(samples):
        with tempfile.TemporaryDirectory(prefix="melix-dataset-registry-probe-") as tmp:
            home = Path(tmp) / "home"
            _snapshot_dir, expected_files = _write_probe_snapshot(home, file_count=file_count)
            helper_calls = 0

            def counted_split(relative_path: str) -> str:
                nonlocal helper_calls
                helper_calls += 1
                return original_split(relative_path)

            def counted_config(relative_path: str) -> str:
                nonlocal helper_calls
                helper_calls += 1
                return original_config(relative_path)

            catalog._inferred_split = counted_split
            catalog._inferred_config = counted_config
            try:
                tracemalloc.start()
                started = time.perf_counter()
                payload = DatasetCatalog(environment={"HOME": os.fspath(home)}).registry_snapshot_payload()
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                _current, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
            finally:
                catalog._inferred_split = original_split
                catalog._inferred_config = original_config
                if tracemalloc.is_tracing():  # pragma: no cover - defensive cleanup after interrupted tracing
                    tracemalloc.stop()

            datasets = payload.get("datasets", [])
            if len(datasets) != 1:  # pragma: no cover - probe guard rail
                raise SystemExit(f"unexpected dataset count: {len(datasets)}")
            dataset = datasets[0]
            if len(dataset.get("files", [])) != expected_files:  # pragma: no cover - probe guard rail
                raise SystemExit("unexpected dataset file count")
            if dataset.get("splits") != ["test", "train", "validation"]:  # pragma: no cover - probe guard rail
                raise SystemExit(f"unexpected splits: {dataset.get('splits')!r}")
            expected_config_count = min(12, file_count) + 1
            if len(dataset.get("configs", [])) != expected_config_count:  # pragma: no cover - probe guard rail
                raise SystemExit(f"unexpected configs: {dataset.get('configs')!r}")
            elapsed_samples.append(elapsed_ms)
            peak_samples.append(float(peak))
            helper_call_samples.append(float(helper_calls))
            file_count_samples.append(float(expected_files))

    return {
        "elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "peak_bytes_mean": statistics.fmean(peak_samples),
        "legacy_inference_helper_calls_mean": statistics.fmean(helper_call_samples),
        "file_count_mean": statistics.fmean(file_count_samples),
        "sample_count": float(samples),
    }


def main() -> int:
    file_count = int(os.environ.get("MELIX_DATASET_REGISTRY_PROBE_FILE_COUNT", "2400"))
    samples = int(os.environ.get("MELIX_DATASET_REGISTRY_PROBE_SAMPLES", "5"))
    metrics = run_probe(file_count=file_count, samples=samples)
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
