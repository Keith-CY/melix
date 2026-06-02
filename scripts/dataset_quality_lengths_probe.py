#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.productization.dataset_preparation import DatasetVersionRequest, _quality_summary  # noqa: E402


def _row(index: int, *, messages: bool) -> dict[str, Any]:
    if messages:
        return {
            "source_segment_id": f"segment-{index:05d}",
            "messages": [
                {"role": "user", "content": f"Question {index} " + "x" * 24},
                {"role": "assistant", "content": f"Answer {index} " + "y" * 48},
            ],
        }
    return {
        "source_segment_id": f"segment-{index:05d}",
        "prompt": f"Prompt {index}",
        "completion": "z" * (32 + (index % 17)),
    }


def measure(*, train_count: int, validation_count: int, samples: int) -> dict[str, float]:
    train_rows = [_row(index, messages=False) for index in range(train_count)]
    validation_rows = [_row(train_count + index, messages=True) for index in range(validation_count)]
    request = DatasetVersionRequest(
        workspace_manifest_path=Path("workspace-manifest.json"),
        ingest_receipt_path=Path("ingest-receipt.json"),
        output_root=Path("datasets"),
        dataset_id="support-chat",
        version_id="support-chat-v1",
    )
    ingest_receipt = {
        "quality_control_summary": {
            "source_record_count": train_count + validation_count,
            "exact_dedup_count": 0,
            "fuzzy_dedup_count": 0,
            "pii_mask_count": 0,
        }
    }

    elapsed_samples: list[float] = []
    summary: dict[str, Any] | None = None
    for _ in range(samples):
        started = time.perf_counter()
        summary = _quality_summary(
            request=request,
            ingest_receipt=ingest_receipt,
            version_id="support-chat-v1",
            train_rows=train_rows,
            validation_rows=validation_rows,
            failed_count=0,
            latency_ms=0.0,
        )
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)

    if summary is None:
        raise AssertionError("quality summary was not measured")
    row_count = train_count + validation_count
    if summary["metrics"]["generated_sample_count"] != row_count:
        raise AssertionError(
            f"expected {row_count} generated samples, got {summary['metrics']['generated_sample_count']}"
        )
    if summary["mean_output_length"] <= 0:
        raise AssertionError("expected positive mean output length")
    if summary["p95_output_length"] <= 0:
        raise AssertionError("expected positive p95 output length")

    return {
        "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
        "elapsed_ms_min": round(min(elapsed_samples), 6),
        "elapsed_ms_p95": round(sorted(elapsed_samples)[int(0.95 * (len(elapsed_samples) - 1))], 6),
        "sample_count": float(samples),
        "train_row_count": float(train_count),
        "validation_row_count": float(validation_count),
        "row_count": float(row_count),
        "mean_output_length": float(summary["mean_output_length"]),
        "p95_output_length": float(summary["p95_output_length"]),
    }


def main() -> int:
    train_count = int(os.environ.get("MELIX_DATASET_QUALITY_LENGTHS_TRAIN_ROWS", "12000"))
    validation_count = int(os.environ.get("MELIX_DATASET_QUALITY_LENGTHS_VALIDATION_ROWS", "3000"))
    samples = int(os.environ.get("MELIX_DATASET_QUALITY_LENGTHS_SAMPLES", "7"))
    print(json.dumps(measure(train_count=train_count, validation_count=validation_count, samples=samples), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
