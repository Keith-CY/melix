#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(os.environ.get("MELIX_LOCAL_JOB_SCAN_REPO_ROOT", Path.cwd()))
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.runtime import local_job_continuation as target  # noqa: E402
from worker.runtime.local_job_continuation import (  # noqa: E402
    LocalJobContinuationRecord,
    LocalJobContinuationStore,
)


def _ready_record(job_id: str) -> LocalJobContinuationRecord:
    return LocalJobContinuationRecord(
        job_id=job_id,
        command=("melix", "local-job", job_id),
        cwd="/workspace",
        log_path=f"/workspace/logs/{job_id}.log",
        session_id=f"session-{job_id}",
        status="completed",
        exit_status=0,
        artifact_paths=(f"/workspace/out/{job_id}.json",),
    )


def _prepare_store(root: Path, *, record_count: int) -> LocalJobContinuationStore:
    store = LocalJobContinuationStore(root)
    for index in range(record_count):
        store.save_record(_ready_record(f"job-{index:05d}"))
    (root / "ignored.json.tmp").write_text("{}\n", encoding="utf-8")
    (root / "notes.txt").write_text("not a record\n", encoding="utf-8")
    (root / "nested.json").mkdir()
    return store


def run_probe(*, record_count: int = 500, samples: int = 5) -> dict[str, float]:
    elapsed_samples: list[float] = []
    candidate_samples: list[float] = []
    receipt_samples: list[float] = []
    scandir_samples: list[float] = []
    glob_samples: list[float] = []
    exists_samples: list[float] = []

    with tempfile.TemporaryDirectory(prefix="melix-local-job-scan-") as tmp:
        store = _prepare_store(Path(tmp), record_count=record_count)
        original_scandir = target.os.scandir
        original_glob = target.Path.glob
        original_exists = target.Path.exists
        try:
            for _ in range(samples):
                scandir_calls = 0
                glob_calls = 0
                exists_calls = 0

                def counted_scandir(path: str | os.PathLike[str]):
                    nonlocal scandir_calls
                    scandir_calls += 1
                    return original_scandir(path)

                def counted_glob(self: Path, pattern: str):
                    nonlocal glob_calls
                    glob_calls += 1
                    return original_glob(self, pattern)

                def counted_exists(self: Path):  # pragma: no cover - regression counter
                    nonlocal exists_calls
                    exists_calls += 1
                    return original_exists(self)

                target.os.scandir = counted_scandir
                target.Path.glob = counted_glob
                target.Path.exists = counted_exists
                started = time.perf_counter()
                scan = store.scan_followup_candidates()
                elapsed_samples.append((time.perf_counter() - started) * 1000.0)
                candidate_samples.append(float(len(scan.candidates)))
                receipt_samples.append(float(len(scan.receipts)))
                scandir_samples.append(float(scandir_calls))
                glob_samples.append(float(glob_calls))
                exists_samples.append(float(exists_calls))
        finally:
            target.os.scandir = original_scandir
            target.Path.glob = original_glob
            target.Path.exists = original_exists

    return {
        "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
        "elapsed_ms_min": round(min(elapsed_samples), 6),
        "candidate_count_mean": statistics.fmean(candidate_samples),
        "receipt_count_mean": statistics.fmean(receipt_samples),
        "scandir_calls_mean": statistics.fmean(scandir_samples),
        "path_glob_calls_mean": statistics.fmean(glob_samples),
        "path_exists_calls_mean": statistics.fmean(exists_samples),
        "record_count": float(record_count),
        "sample_count": float(samples),
    }


def run_projection_probe(*, record_count: int = 250, samples: int = 5) -> dict[str, float]:
    elapsed_samples: list[float] = []
    projection_samples: list[float] = []
    followup_message_samples: list[float] = []
    receipt_samples: list[float] = []

    for _ in range(samples):
        with tempfile.TemporaryDirectory(prefix="melix-local-job-projection-") as tmp:
            store = _prepare_store(Path(tmp), record_count=record_count)
            followup_session_ids = {
                f"job-{index:05d}": f"followup-job-{index:05d}"
                for index in range(record_count)
            }
            completion_summaries = {
                f"job-{index:05d}": {
                    "status": "completed",
                    "summary": f"Redacted completion summary {index}",
                }
                for index in range(record_count)
            }
            owner_scope_checked = {f"job-{index:05d}": True for index in range(record_count)}

            started = time.perf_counter()
            projection_batch = target.project_local_job_session_followups(
                store,
                followup_session_ids_by_job_id=followup_session_ids,
                completion_summaries_by_job_id=completion_summaries,
                owner_scope_checked_by_job_id=owner_scope_checked,
            )
            elapsed_samples.append((time.perf_counter() - started) * 1000.0)
            projection_samples.append(float(len(projection_batch.projections)))
            followup_message_samples.append(float(len(projection_batch.followup_messages)))
            receipt_samples.append(float(len(projection_batch.receipts)))

    return {
        "projection_elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
        "projection_elapsed_ms_min": round(min(elapsed_samples), 6),
        "projection_count_mean": statistics.fmean(projection_samples),
        "projection_followup_message_count_mean": statistics.fmean(followup_message_samples),
        "projection_receipt_count_mean": statistics.fmean(receipt_samples),
    }


def main() -> int:
    record_count = int(os.environ.get("MELIX_LOCAL_JOB_SCAN_RECORDS", "500"))
    samples = int(os.environ.get("MELIX_LOCAL_JOB_SCAN_SAMPLES", "5"))
    projection_record_count = int(
        os.environ.get("MELIX_LOCAL_JOB_PROJECTION_RECORDS", "250")
    )
    metrics = run_probe(record_count=record_count, samples=samples)
    metrics.update(
        run_projection_probe(record_count=projection_record_count, samples=samples)
    )
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
