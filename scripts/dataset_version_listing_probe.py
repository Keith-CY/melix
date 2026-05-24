#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.productization.dataset_preparation import list_dataset_versions  # noqa: E402


def _write_version_manifest(path: Path, *, version_id: str, created_at: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "dataset_id": "support-chat",
                "version_id": version_id,
                "created_at": created_at,
                "status": "ready",
                "train_count": 2,
                "validation_count": 1,
                "failed_count": 0,
                "quality_summary_path": str(path.parent / "quality-summary.json"),
            }
        ),
        encoding="utf-8",
    )


def main() -> int:
    version_count = int(os.environ.get("MELIX_DATASET_VERSION_LISTING_PROBE_COUNT", "2500"))
    sample_count = int(os.environ.get("MELIX_DATASET_VERSION_LISTING_PROBE_SAMPLES", "7"))
    elapsed_samples: list[float] = []

    with tempfile.TemporaryDirectory(prefix="melix-dataset-version-listing-probe-") as temp_dir:
        temp_root = Path(temp_dir)
        output_root = temp_root / "datasets"
        versions_root = output_root / "support-chat" / "versions"
        for index in range(version_count):
            version_id = f"support-chat-v{index:05d}"
            _write_version_manifest(
                versions_root / version_id / "dataset-version.json",
                version_id=version_id,
                created_at=f"2026-05-24T00:{index % 60:02d}:{index // 60 % 60:02d}Z",
            )
        # Noise entries should not be counted.
        (versions_root / "not-a-version.txt").write_text("ignored", encoding="utf-8")
        (versions_root / "empty-dir").mkdir(parents=True, exist_ok=True)

        listing = None
        for _ in range(sample_count):
            started = time.perf_counter()
            listing = list_dataset_versions(
                workspace_manifest_path=temp_root / "workspace-manifest.json",
                output_root=output_root,
                dataset_id="support-chat",
            )
            elapsed_samples.append((time.perf_counter() - started) * 1000.0)

    if listing is None:
        raise AssertionError("listing was not measured")
    if listing["metrics"]["dataset_version_count"] != version_count:
        raise AssertionError(
            f"expected {version_count} versions, got {listing['metrics']['dataset_version_count']}"
        )
    print(
        json.dumps(
            {
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "elapsed_ms_min": round(min(elapsed_samples), 6),
                "elapsed_ms_p95": round(sorted(elapsed_samples)[int(0.95 * (len(elapsed_samples) - 1))], 6),
                "sample_count": float(sample_count),
                "version_count": float(version_count),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
