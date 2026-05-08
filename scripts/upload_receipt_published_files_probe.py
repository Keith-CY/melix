#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
from typing import Any


def _seed_tree(root: Path, *, directory_count: int, files_per_directory: int) -> int:
    total = 0
    for directory_index in range(directory_count):
        directory = root / f"shard-{directory_index:04d}"
        directory.mkdir(parents=True, exist_ok=True)
        for file_index in range(files_per_directory):
            (directory / f"part-{file_index:04d}.safetensors").write_bytes(b"melix")
            total += 1
    (root / "README.md").write_text("# Melix synthetic publish bundle\n", encoding="utf-8")
    return total + 1


def _measure_special_entry_follow_dir_checks(module: Any, *, sample_count: int) -> float:
    source_root = Path("/tmp/melix-upload-receipt-special-entries")
    followed_dir_checks = 0

    class FakeDirEntry:
        def __init__(
            self,
            name: str,
            *,
            is_file: bool = False,
            is_symlink: bool = False,
            follows_to_dir: bool = False,
        ) -> None:
            self.name = name
            self.path = os.fspath(source_root / name)
            self._is_file = is_file
            self._is_symlink = is_symlink
            self._follows_to_dir = follows_to_dir

        def is_dir(self, *, follow_symlinks: bool = True) -> bool:
            nonlocal followed_dir_checks
            if follow_symlinks:
                if not self._is_symlink:
                    followed_dir_checks += 1  # pragma: no cover - legacy/base compatibility path
                return self._follows_to_dir
            return False

        def is_file(self, *, follow_symlinks: bool = True) -> bool:
            return self._is_file

        def is_symlink(self) -> bool:
            return self._is_symlink

    class FakeScandir:
        def __init__(self, path: str) -> None:
            self._path = path

        def __enter__(self):
            if self._path == os.fspath(source_root):
                return iter(
                    [
                        FakeDirEntry("regular.bin", is_file=True),
                        FakeDirEntry("special-device"),
                        FakeDirEntry("file-link", is_symlink=True),
                        FakeDirEntry("dir-link", is_symlink=True, follows_to_dir=True),
                    ]
                )
            return iter(())  # pragma: no cover - only used for unexpected nested scans

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    original_scandir = module.os.scandir
    module.os.scandir = FakeScandir
    try:
        for _ in range(sample_count):
            published_files = module.UploadReceiptPipeline._collect_published_file_list(source_root)
            if published_files != ["file-link", "regular.bin", "special-device"]:
                raise RuntimeError(  # pragma: no cover - defensive probe guard
                    f"unexpected special-entry payload: {published_files!r}"
                )
    finally:
        module.os.scandir = original_scandir
    return followed_dir_checks / sample_count


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(repo_root / "services/mlx-worker-python"))

    from worker.model_ops import upload_receipt_pipeline
    from worker.model_ops.upload_receipt_pipeline import UploadReceiptPipeline

    elapsed_samples: list[float] = []
    file_counts: list[int] = []
    directory_count = 180
    files_per_directory = 40
    sample_count = 5

    with tempfile.TemporaryDirectory(prefix="melix-upload-receipt-probe-") as temp_dir:
        source_root = Path(temp_dir) / "publish-bundle"
        expected_file_count = _seed_tree(
            source_root,
            directory_count=directory_count,
            files_per_directory=files_per_directory,
        )
        for _ in range(sample_count):
            started = time.perf_counter()
            published_files = UploadReceiptPipeline._collect_published_file_list(source_root)
            elapsed_samples.append((time.perf_counter() - started) * 1000.0)
            file_counts.append(len(published_files))
            if len(published_files) != expected_file_count:
                raise RuntimeError(
                    f"expected {expected_file_count} published files, got {len(published_files)}"
                )

        special_entry_follow_dir_checks_mean = _measure_special_entry_follow_dir_checks(
            upload_receipt_pipeline,
            sample_count=sample_count,
        )

    print(
        json.dumps(
            {
                "directory_count": float(directory_count),
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "elapsed_ms_min": round(min(elapsed_samples), 6),
                "files_per_directory": float(files_per_directory),
                "published_file_count": float(file_counts[-1]),
                "sample_count": float(sample_count),
                "special_entry_follow_dir_checks_mean": round(
                    special_entry_follow_dir_checks_mean,
                    6,
                ),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
