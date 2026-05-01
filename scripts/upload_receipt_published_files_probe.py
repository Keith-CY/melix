#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import statistics
import sys
import tempfile
import time


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


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(repo_root / "services/mlx-worker-python"))

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

    print(
        json.dumps(
            {
                "directory_count": float(directory_count),
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "elapsed_ms_min": round(min(elapsed_samples), 6),
                "files_per_directory": float(files_per_directory),
                "published_file_count": float(file_counts[-1]),
                "sample_count": float(sample_count),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
