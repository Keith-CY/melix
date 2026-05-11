from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.runtime.runtime_utils import estimate_model_weight_resident_bytes


def _build_bundle(root: Path, file_count: int) -> tuple[Path, int]:
    bundle = root / "flat-model"
    bundle.mkdir()
    expected = 0
    for index in range(file_count):
        suffix = ".safetensors" if index % 2 == 0 else ".txt"
        payload = b"w" * ((index % 17) + 1)
        path = bundle / f"artifact-{index:05d}{suffix}"
        path.write_bytes(payload)
        if suffix == ".safetensors":
            expected += len(payload)
    return bundle, expected


def _sample(bundle: Path, expected: int, iterations: int) -> tuple[float, int, int]:
    started = time.perf_counter()
    checksum = 0
    for _ in range(iterations):
        observed = estimate_model_weight_resident_bytes(str(bundle))
        if observed != expected:
            raise RuntimeError(f"unexpected resident byte estimate: {observed} != {expected}")
        checksum += observed
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return elapsed_ms, checksum, expected


def main() -> int:
    file_count = int(os.environ.get("MELIX_RUNTIME_UTILS_WEIGHT_FILES", "3000"))
    iterations = int(os.environ.get("MELIX_RUNTIME_UTILS_WEIGHT_ITERATIONS", "8"))
    sample_count = int(os.environ.get("MELIX_RUNTIME_UTILS_WEIGHT_SAMPLES", "5"))
    elapsed: list[float] = []
    peaks: list[float] = []
    checksum = 0
    expected = 0
    with tempfile.TemporaryDirectory() as directory:
        bundle, expected = _build_bundle(Path(directory), file_count)
        for _ in range(sample_count):
            tracemalloc.start()
            elapsed_ms, checksum, expected = _sample(bundle, expected, iterations)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            elapsed.append(elapsed_ms)
            peaks.append(float(peak))
    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(elapsed),
                "peak_bytes_mean": statistics.fmean(peaks),
                "file_count": float(file_count),
                "iterations": float(iterations),
                "expected_bytes": float(expected),
                "checksum": float(checksum),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
