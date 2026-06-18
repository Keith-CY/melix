from __future__ import annotations

import json
import statistics
import tempfile
import time
from pathlib import Path

from worker.productization.macos_app_bundle import _prune_python_package_baggage


PACKAGE_COUNT = 400
PRUNABLE_DIR_NAMES = ("tests", "test", "testing", "docs", "doc", "__pycache__")
KEPT_FILE_COUNT = 3
SAMPLE_COUNT = 9


def _build_site_packages(root: Path) -> None:
    root.mkdir()
    for index in range(PACKAGE_COUNT):
        package = root / f"package_{index:04d}"
        package.mkdir()
        for dirname in PRUNABLE_DIR_NAMES:
            prunable = package / dirname
            prunable.mkdir()
            (prunable / "fixture.txt").write_text("x" * 64, encoding="utf-8")
        for file_index in range(KEPT_FILE_COUNT):
            (package / f"module_{file_index}.py").write_text("VALUE = 1\n", encoding="utf-8")


def main() -> None:
    elapsed_samples: list[float] = []
    pruned_count = 0
    bytes_saved = 0
    for _ in range(SAMPLE_COUNT):
        with tempfile.TemporaryDirectory() as tmp:
            site_packages = Path(tmp) / "site-packages"
            _build_site_packages(site_packages)
            started_at = time.perf_counter()
            result = _prune_python_package_baggage(site_packages)
            elapsed_samples.append((time.perf_counter() - started_at) * 1000.0)
            pruned_count = result["directories_pruned"]
            bytes_saved = result["bytes_saved"]

    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.mean(elapsed_samples),
                "elapsed_ms_min": min(elapsed_samples),
                "elapsed_ms_p95": statistics.quantiles(elapsed_samples, n=20)[18],
                "sample_count": float(SAMPLE_COUNT),
                "package_count": float(PACKAGE_COUNT),
                "pruned_count": float(pruned_count),
                "bytes_saved": float(bytes_saved),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
