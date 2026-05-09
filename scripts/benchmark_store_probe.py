#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
import tracemalloc

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.productization.benchmark_schemas import (  # noqa: E402
    build_benchmark_matrix_job,
    build_benchmark_matrix_request_row,
    build_benchmark_matrix_summary_row,
)
from worker.productization.benchmark_store import BenchmarkStore  # noqa: E402


def _count_text_lines(path: Path) -> float:
    with path.open("r", encoding="utf-8") as handle:
        return float(sum(1 for _ in handle))


def _build_summary_rows(job_id: str, summary_count: int) -> tuple[object, ...]:
    return tuple(
        build_benchmark_matrix_summary_row(
            job_id=job_id,
            task_kind="text-generation",
            source_repo="synthetic/benchmark-store",
            model_id="melix-dev-text",
            suite_id=f"suite-{index % 8}",
            context_length=1024 + (index % 4) * 512,
            generation_length=128,
            batch_size=1 + (index % 4),
            cache_profile="cold",
            reasoning_mode="enabled" if index % 2 else "disabled",
            structured_output_mode="plain_text",
            concurrency_level=1 + (index % 3),
            repeats=3,
            requests=24,
            duration_seconds=0,
            ttft_mean_ms=24.45 + (index % 5),
            ttft_std_ms=1.2,
            request_latency_mean_ms=88.4 + (index % 7),
            request_latency_std_ms=3.1,
            prefill_tokens_per_second_mean=1400.0,
            decode_tokens_per_second_mean=58.2,
            throughput_requests_per_second=3.8,
            throughput_tokens_per_second=221.5,
            success_rate=1.0,
            peak_memory_bytes_max=2_147_483_648 + index,
            queue_wait_mean_ms=5.1,
            queue_wait_p95_ms=9.2,
            created_at_unix_ms=101 + index,
        )
        for index in range(summary_count)
    )


def _build_request_rows(job_id: str, request_count: int) -> tuple[object, ...]:
    return tuple(
        build_benchmark_matrix_request_row(
            job_id=job_id,
            cell_id=f"cell-{index}",
            task_kind="text-generation",
            suite_id=f"suite-{index % 8}",
            context_length=1024 + (index % 4) * 512,
            generation_length=128,
            batch_size=1 + (index % 4),
            cache_profile="cold",
            reasoning_mode="enabled" if index % 2 else "disabled",
            structured_output_mode="plain_text",
            concurrency_level=1 + (index % 3),
            repeat_index=index % 3,
            request_index=index,
            ttft_ms=24.45 + (index % 5),
            request_latency_ms=88.4 + (index % 7),
            prefill_tokens_per_second=1400.0,
            decode_tokens_per_second=58.2,
            queue_wait_ms=5.1,
            peak_memory_bytes=2_147_483_648 + index,
            status="completed",
            error_code="",
            created_at_unix_ms=101 + index,
        )
        for index in range(request_count)
    )


def main() -> int:
    store = BenchmarkStore()
    job_id = "bench-matrix-probe"
    summary_count = 750
    request_count = 6000
    sample_count = 3
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    summary_line_count = 0.0
    request_line_count = 0.0
    csv_line_count = 0.0

    summary_rows = _build_summary_rows(job_id, summary_count)
    request_rows = _build_request_rows(job_id, request_count)

    for _ in range(sample_count):
        with tempfile.TemporaryDirectory(prefix="melix-pr-perf-benchmark-store-") as temp_dir:
            jobs_root = Path(temp_dir) / "bench" / "matrix-runs" / job_id
            job = build_benchmark_matrix_job(
                job_id=job_id,
                model_id="melix-dev-text",
                task_kind="text-generation",
                source_repo="synthetic/benchmark-store",
                suite_ids=tuple(sorted({f"suite-{index % 8}" for index in range(summary_count)})),
                status="completed",
                output_dir=str(jobs_root),
            )
            tracemalloc.start()
            started = time.perf_counter()
            persisted = store.persist_benchmark_matrix(
                jobs_root=jobs_root,
                job=job,
                summary_rows=summary_rows,
                request_rows=request_rows,
            )
            elapsed_samples.append((time.perf_counter() - started) * 1000.0)
            _, peak_bytes = tracemalloc.get_traced_memory()
            peak_samples.append(float(peak_bytes))
            tracemalloc.stop()

            summary_line_count = _count_text_lines(persisted["summary_jsonl"])
            request_line_count = _count_text_lines(persisted["requests_jsonl"])
            csv_line_count = _count_text_lines(persisted["requests_csv"])
            if summary_line_count != float(summary_count):
                raise RuntimeError(f"unexpected summary row count: {summary_line_count}")
            if request_line_count != float(request_count):
                raise RuntimeError(f"unexpected request row count: {request_line_count}")
            if csv_line_count != float(request_count + 1):
                raise RuntimeError(f"unexpected request csv line count: {csv_line_count}")

    print(
        json.dumps(
            {
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "peak_bytes_mean": round(statistics.fmean(peak_samples), 1),
                "request_csv_line_count": csv_line_count,
                "request_row_count": request_line_count,
                "sample_count": float(sample_count),
                "summary_row_count": summary_line_count,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
