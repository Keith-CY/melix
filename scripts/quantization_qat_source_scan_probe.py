from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

REPO_ROOT = Path(os.environ.get("MELIX_QAT_SOURCE_SCAN_REPO_ROOT") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.model_ops import quantization_pipeline
from worker.model_ops.quantization_pipeline import _source_artifact_files_for_qat


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def _write_source_tree(root: Path, *, file_count: int) -> list[Path]:
    expected: list[Path] = []
    for index in range(file_count):
        parent = root / f"shard-{index % 32:02d}" / f"block-{index % 8:02d}"
        parent.mkdir(parents=True, exist_ok=True)
        suffix = ".safetensors" if index % 2 else ".json"
        path = parent / f"artifact-{index:05d}{suffix}"
        path.write_bytes((f"melix-qatsource-{index}\n" * 2).encode("utf-8"))
        expected.append(path)
    (root / "empty-dir").mkdir(parents=True, exist_ok=True)
    return sorted(expected)


def main() -> int:
    file_count = _int_env("MELIX_QAT_SOURCE_SCAN_PROBE_FILES", 4000)
    sample_count = _int_env("MELIX_QAT_SOURCE_SCAN_PROBE_SAMPLES", 5)
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    scandir_samples: list[float] = []
    rglob_samples: list[float] = []

    with tempfile.TemporaryDirectory(prefix="melix-qat-source-scan-probe-") as temp_dir:
        source_root = Path(temp_dir) / "merged-adapter"
        expected = _write_source_tree(source_root, file_count=file_count)
        original_scandir = quantization_pipeline.os.scandir
        original_rglob = Path.rglob

        for _ in range(sample_count):
            scandir_calls = 0
            rglob_calls = 0

            def tracked_scandir(path: str | bytes | os.PathLike[str] | os.PathLike[bytes] | int):
                nonlocal scandir_calls
                scandir_calls += 1
                return original_scandir(path)

            def tracked_rglob(self: Path, pattern: str):
                nonlocal rglob_calls
                rglob_calls += 1
                return original_rglob(self, pattern)

            quantization_pipeline.os.scandir = tracked_scandir
            Path.rglob = tracked_rglob  # type: ignore[method-assign]
            try:
                tracemalloc.start()
                started = time.perf_counter()
                files = _source_artifact_files_for_qat(source_root)
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
            finally:
                quantization_pipeline.os.scandir = original_scandir
                Path.rglob = original_rglob  # type: ignore[method-assign]
                if tracemalloc.is_tracing():
                    tracemalloc.stop()

            if files != expected:
                raise SystemExit("unexpected QAT source file ordering/count")
            elapsed_samples.append(elapsed_ms)
            peak_samples.append(float(peak))
            scandir_samples.append(float(scandir_calls))
            rglob_samples.append(float(rglob_calls))

    print(
        json.dumps(
            {
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "elapsed_ms_min": round(min(elapsed_samples), 6),
                "peak_bytes_mean": round(statistics.fmean(peak_samples), 3),
                "scandir_calls_mean": round(statistics.fmean(scandir_samples), 3),
                "rglob_calls_mean": round(statistics.fmean(rglob_samples), 3),
                "file_count": float(file_count),
                "sample_count": float(sample_count),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
