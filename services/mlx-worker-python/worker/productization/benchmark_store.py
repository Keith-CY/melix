from __future__ import annotations

import json
from pathlib import Path

from worker.productization.benchmark_export import (
    build_benchmark_matrix_requests_csv,
    build_benchmark_matrix_summary_csv,
)
from worker.productization.benchmark_schemas import (
    BenchmarkMatrixJob,
    BenchmarkMatrixRequestRow,
    BenchmarkMatrixSummaryRow,
    ServingBenchmarkJob,
    ServingBenchmarkResult,
)


class BenchmarkStore:
    def persist_serving_benchmark(
        self,
        *,
        jobs_root: Path,
        job: ServingBenchmarkJob,
        results: tuple[ServingBenchmarkResult, ...],
    ) -> dict[str, Path]:
        jobs_root.mkdir(parents=True, exist_ok=True)

        job_path = jobs_root / "bench-job.json"
        job_path.write_text(
            json.dumps(job.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )

        persisted: dict[str, Path] = {"job": job_path}
        for result in results:
            result_path = jobs_root / f"bench-result-{result.suite}.json"
            result_path.write_text(
                json.dumps(result.to_dict(), indent=2) + "\n",
                encoding="utf-8",
            )
            persisted[result.suite] = result_path

        return persisted

    def persist_benchmark_matrix(
        self,
        *,
        jobs_root: Path,
        job: BenchmarkMatrixJob,
        summary_rows: tuple[BenchmarkMatrixSummaryRow, ...],
        request_rows: tuple[BenchmarkMatrixRequestRow, ...],
    ) -> dict[str, Path]:
        jobs_root.mkdir(parents=True, exist_ok=True)

        job_path = jobs_root / "bench-matrix-job.json"
        job_path.write_text(
            json.dumps(job.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )

        summary_jsonl_path = jobs_root / "bench-matrix-summary.jsonl"
        summary_jsonl_path.write_text(
            "".join(json.dumps(row.to_dict()) + "\n" for row in summary_rows),
            encoding="utf-8",
        )

        requests_jsonl_path = jobs_root / "bench-matrix-requests.jsonl"
        requests_jsonl_path.write_text(
            "".join(json.dumps(row.to_dict()) + "\n" for row in request_rows),
            encoding="utf-8",
        )

        summary_csv_path = jobs_root / "bench-matrix-summary.csv"
        summary_csv_path.write_text(
            build_benchmark_matrix_summary_csv(
                {"benchmark_matrix_summary_rows": [row.to_dict() for row in summary_rows]}
            ),
            encoding="utf-8",
        )

        requests_csv_path = jobs_root / "bench-matrix-requests.csv"
        requests_csv_path.write_text(
            build_benchmark_matrix_requests_csv(
                {"benchmark_matrix_request_rows": [row.to_dict() for row in request_rows]}
            ),
            encoding="utf-8",
        )

        return {
            "job": job_path,
            "summary_jsonl": summary_jsonl_path,
            "summary_csv": summary_csv_path,
            "requests_jsonl": requests_jsonl_path,
            "requests_csv": requests_csv_path,
        }
