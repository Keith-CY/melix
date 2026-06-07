from __future__ import annotations

import json
import statistics
import tempfile
import time
from pathlib import Path

from worker.productization.macos_app_bundle import _path_size_bytes

FILE_COUNT = 2500
SUBDIR_COUNT = 25
SAMPLE_COUNT = 9


def main() -> None:
    elapsed_samples: list[float] = []
    expected_size = 0
    with tempfile.TemporaryDirectory(prefix="melix-macos-path-size-probe-") as temp_dir:
        base = Path(temp_dir)
        root = base / "payload"
        root.mkdir()
        external = base / "external"
        external.mkdir()
        (external / "ignored.txt").write_text("ignored\n", encoding="utf-8")
        directory_link = root / "linked-dir"
        directory_link.symlink_to(external, target_is_directory=True)
        expected_size += directory_link.lstat().st_size

        for directory_index in range(SUBDIR_COUNT):
            directory = root / f"package_{directory_index:03d}"
            directory.mkdir()
            for file_index in range(FILE_COUNT // SUBDIR_COUNT):
                path = directory / f"module_{file_index:04d}.py"
                path.write_text(
                    f"VALUE = {directory_index * file_index}\n",
                    encoding="utf-8",
                )
                expected_size += path.lstat().st_size

        measured_size = 0
        for _ in range(SAMPLE_COUNT):
            started = time.perf_counter()
            measured_size = _path_size_bytes(root)
            elapsed_samples.append((time.perf_counter() - started) * 1000.0)
            if measured_size != expected_size:
                raise AssertionError(f"expected {expected_size} bytes, got {measured_size}")

    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.mean(elapsed_samples),
                "elapsed_ms_min": min(elapsed_samples),
                "elapsed_ms_p95": sorted(elapsed_samples)[int(len(elapsed_samples) * 0.95) - 1],
                "file_count": float(FILE_COUNT),
                "sample_count": float(SAMPLE_COUNT),
                "measured_size_bytes": float(measured_size),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
