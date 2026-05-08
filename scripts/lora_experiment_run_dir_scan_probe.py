from __future__ import annotations

import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path.cwd()
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.productization import lora_experiment_store as store_module  # noqa: E402

RUN_COUNT = 8_000
NOISE_COUNT = 1_000
ITERATIONS = 24
SAMPLES = 5
TRAIN_ROOT = Path("/tmp/melix-lora-scan-probe/train_lora")


class FakeEntry:
    __slots__ = ("name", "_path", "_is_dir")

    def __init__(self, name: str, *, is_dir: bool = True) -> None:
        self.name = name
        self._path = str(TRAIN_ROOT / name)
        self._is_dir = is_dir

    @property
    def path(self) -> str:
        global path_attr_reads
        path_attr_reads += 1
        return self._path

    def is_dir(self) -> bool:
        return self._is_dir


class FakeScandir:
    def __init__(self, path: object) -> None:
        self.path = path

    def __enter__(self) -> Iterator[FakeEntry]:
        return iter(fake_entries)

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


fake_entries = tuple(
    [FakeEntry(f"model-ops-{idx:05d}") for idx in range(RUN_COUNT, 0, -1)]
    + [FakeEntry(f"noise-{idx:05d}") for idx in range(NOISE_COUNT)]
    + [FakeEntry(f"model-ops-file-{idx:05d}", is_dir=False) for idx in range(NOISE_COUNT)]
)
path_attr_reads = 0


def run_sample() -> dict[str, float]:
    global path_attr_reads
    path_attr_reads = 0
    original_scandir = store_module.os.scandir
    store_module.os.scandir = FakeScandir  # type: ignore[assignment]
    tracemalloc.start()
    started = time.perf_counter()
    try:
        result_count = 0
        for _ in range(ITERATIONS):
            result = store_module._iter_lora_run_dirs(TRAIN_ROOT)
            result_count = len(result)
            if result_count != RUN_COUNT:
                raise AssertionError(f"unexpected run dir count: {result_count}")
            if result[0].name != "model-ops-00001" or result[-1].name != f"model-ops-{RUN_COUNT:05d}":
                raise AssertionError("run dirs are not sorted by name")
    finally:
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        store_module.os.scandir = original_scandir
    return {
        "elapsed_ms": elapsed * 1000,
        "peak_bytes": float(peak),
        "path_attr_reads": float(path_attr_reads),
    }


def main() -> None:
    samples = [run_sample() for _ in range(SAMPLES)]
    payload = {
        "run_dir_count": RUN_COUNT,
        "iteration_count": ITERATIONS,
        "sample_count": SAMPLES,
        "elapsed_ms_mean": statistics.fmean(sample["elapsed_ms"] for sample in samples),
        "peak_bytes_mean": statistics.fmean(sample["peak_bytes"] for sample in samples),
        "path_attr_reads_mean": statistics.fmean(sample["path_attr_reads"] for sample in samples),
    }
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
