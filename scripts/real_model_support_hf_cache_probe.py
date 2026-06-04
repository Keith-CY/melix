#!/usr/bin/env python3
from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

SNAPSHOT_COUNT = 6000
SAMPLE_COUNT = 7
WEIGHT_FILE_COUNT = 20_000
MODEL_ID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
LATEST_SNAPSHOT = f"snapshot-{SNAPSHOT_COUNT - 1:05d}"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _build_cache(home: Path) -> Path:
    snapshots_root = (
        home
        / ".cache"
        / "huggingface"
        / "hub"
        / "models--mlx-community--Qwen3.5-0.8B-OptiQ-4bit"
        / "snapshots"
    )
    snapshots_root.mkdir(parents=True)
    for index in range(SNAPSHOT_COUNT):
        (snapshots_root / f"snapshot-{index:05d}").mkdir()
    (snapshots_root / "not-a-directory").write_text("ignored\n", encoding="utf-8")
    return snapshots_root


def _build_weight_directory(root: Path) -> Path:
    weight_dir = root / "weights"
    weight_dir.mkdir()
    for index in range(WEIGHT_FILE_COUNT - 1):
        (weight_dir / f"config-{index:05d}.json").write_text("{}\n", encoding="utf-8")
    (weight_dir / "model.safetensors").write_bytes(b"weights")
    return weight_dir


def _measure_weight_scan(weight_dir: Path, has_recognized_model_weight_files) -> tuple[float, float]:
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    for _ in range(SAMPLE_COUNT):
        tracemalloc.start()
        started = time.perf_counter()
        has_weights = has_recognized_model_weight_files(weight_dir)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if not has_weights:
            raise RuntimeError("synthetic weight directory was not recognized")
        elapsed_samples.append(elapsed_ms)
        peak_samples.append(float(peak))
    return round(statistics.fmean(elapsed_samples), 6), round(statistics.fmean(peak_samples), 1)


def _measure() -> dict[str, float]:
    repo_root = _repo_root()
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(repo_root / "services/mlx-worker-python"))

    from scripts.real_model_support import (
        _has_recognized_model_weight_files,
        resolve_real_small_text_model_source,
    )

    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    selected_snapshots: set[str] = set()

    with tempfile.TemporaryDirectory() as tmpdir:
        home = Path(tmpdir) / "home"
        snapshots_root = _build_cache(home)
        environment = {"HOME": str(home)}

        for _ in range(SAMPLE_COUNT):
            tracemalloc.start()
            started = time.perf_counter()
            source = resolve_real_small_text_model_source(
                environment=environment,
                allow_managed_root=False,
                allow_hf_cache=True,
            )
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            elapsed_samples.append(elapsed_ms)
            peak_samples.append(float(peak))
            selected_snapshots.add(Path(source.local_model_path).name)

        if selected_snapshots != {LATEST_SNAPSHOT}:
            raise RuntimeError(f"unexpected selected snapshots: {sorted(selected_snapshots)}")
        if len(tuple(snapshots_root.iterdir())) != SNAPSHOT_COUNT + 1:
            raise RuntimeError("synthetic cache was not built with the expected snapshot count")
        weight_dir = _build_weight_directory(Path(tmpdir))
        weight_elapsed_ms, weight_peak_bytes = _measure_weight_scan(
            weight_dir,
            _has_recognized_model_weight_files,
        )

    return {
        "sample_count": float(SAMPLE_COUNT),
        "snapshot_count": float(SNAPSHOT_COUNT),
        "selected_latest_snapshot": float(SNAPSHOT_COUNT - 1),
        "weight_scan_elapsed_ms_mean": weight_elapsed_ms,
        "weight_file_count": float(WEIGHT_FILE_COUNT),
    }


def main() -> int:
    print(json.dumps(_measure(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
