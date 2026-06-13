from __future__ import annotations

import json
import statistics
import tempfile
import time
from pathlib import Path

from worker.productization.macos_app_bundle import _prune_python_runtime_baggage

RUNTIME_PACKAGE_COUNT = 180
PRUNABLE_DIR_NAMES = ("__pycache__", "ensurepip")
ARCHIVE_COUNT = 120
KEPT_MODULE_COUNT = 3
SAMPLE_COUNT = 9


def _build_python_runtime(root: Path) -> None:
    runtime_lib = root / "lib" / "python3.12"
    runtime_lib.mkdir(parents=True)
    include = root / "include"
    include.mkdir()
    (include / "Python.h").write_text("/* header */\n", encoding="utf-8")

    for package_index in range(RUNTIME_PACKAGE_COUNT):
        package = runtime_lib / f"package_{package_index:04d}"
        package.mkdir()
        for dirname in PRUNABLE_DIR_NAMES:
            prunable = package / dirname
            prunable.mkdir()
            (prunable / "payload.pyc").write_bytes(b"x" * 96)
        for module_index in range(KEPT_MODULE_COUNT):
            (package / f"module_{module_index}.py").write_text("VALUE = 1\n", encoding="utf-8")

    for archive_index in range(ARCHIVE_COUNT):
        (root / f"libpython3.12-{archive_index:04d}.a").write_bytes(b"archive" * 32)


def main() -> None:
    elapsed_samples: list[float] = []
    directories_pruned = 0
    files_pruned = 0
    bytes_saved = 0
    for _ in range(SAMPLE_COUNT):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / "python-runtime"
            _build_python_runtime(runtime)
            started_at = time.perf_counter()
            result = _prune_python_runtime_baggage(runtime)
            elapsed_samples.append((time.perf_counter() - started_at) * 1000.0)
            directories_pruned = result["directories_pruned"]
            files_pruned = result["files_pruned"]
            bytes_saved = result["bytes_saved"]

    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.mean(elapsed_samples),
                "elapsed_ms_min": min(elapsed_samples),
                "elapsed_ms_p95": statistics.quantiles(elapsed_samples, n=20)[18],
                "sample_count": float(SAMPLE_COUNT),
                "runtime_package_count": float(RUNTIME_PACKAGE_COUNT),
                "directories_pruned": float(directories_pruned),
                "files_pruned": float(files_pruned),
                "bytes_saved": float(bytes_saved),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
