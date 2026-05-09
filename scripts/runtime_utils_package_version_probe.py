from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.runtime import runtime_utils


def main() -> int:
    iterations = 60000
    sample_count = 5
    package_names = ("mlx", "mlx-lm", "mlx-vlm")
    elapsed_samples: list[float] = []
    version_call_samples: list[int] = []
    original_version = runtime_utils.importlib.metadata.version

    for _ in range(sample_count):
        if hasattr(runtime_utils, "clear_installed_package_version_cache"):
            runtime_utils.clear_installed_package_version_cache()
        version_calls = 0

        def tracked_version(package_name: str) -> str:
            nonlocal version_calls
            version_calls += 1
            return f"{package_name}-probe-version"

        runtime_utils.importlib.metadata.version = tracked_version
        started = time.perf_counter()
        try:
            checksum = 0
            for index in range(iterations):
                package_name = package_names[index % len(package_names)]
                checksum += len(runtime_utils.installed_package_version(package_name))
            if checksum <= 0:
                raise SystemExit("unexpected empty package-version checksum")
        finally:
            elapsed_samples.append((time.perf_counter() - started) * 1000.0)
            version_call_samples.append(version_calls)
            runtime_utils.importlib.metadata.version = original_version
            if hasattr(runtime_utils, "clear_installed_package_version_cache"):
                runtime_utils.clear_installed_package_version_cache()

    metrics = {
        "elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "metadata_version_calls_mean": statistics.fmean(version_call_samples),
        "iterations_per_sample": float(iterations),
        "package_count": float(len(package_names)),
        "sample_count": float(sample_count),
    }
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
