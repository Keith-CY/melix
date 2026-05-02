from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from pathlib import Path

from worker.productization.benchmark_export import (
    _canonical_benchmark_matrix_request_columns,
    _canonical_benchmark_matrix_summary_columns,
    _csv_value,
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
        summary_csv_path = jobs_root / "bench-matrix-summary.csv"
        self._write_jsonl_and_csv(
            jsonl_path=summary_jsonl_path,
            csv_path=summary_csv_path,
            rows=summary_rows,
            fieldnames=_canonical_benchmark_matrix_summary_columns(),
        )

        requests_jsonl_path = jobs_root / "bench-matrix-requests.jsonl"
        requests_csv_path = jobs_root / "bench-matrix-requests.csv"
        self._write_jsonl_and_csv(
            jsonl_path=requests_jsonl_path,
            csv_path=requests_csv_path,
            rows=request_rows,
            fieldnames=_canonical_benchmark_matrix_request_columns(),
        )

        return {
            "job": job_path,
            "summary_jsonl": summary_jsonl_path,
            "summary_csv": summary_csv_path,
            "requests_jsonl": requests_jsonl_path,
            "requests_csv": requests_csv_path,
        }

    @staticmethod
    def _write_jsonl_and_csv(
        *,
        jsonl_path: Path,
        csv_path: Path,
        rows: Iterable[BenchmarkMatrixSummaryRow | BenchmarkMatrixRequestRow],
        fieldnames: list[str],
    ) -> None:
        with (
            jsonl_path.open("w", encoding="utf-8") as jsonl_handle,
            csv_path.open("w", encoding="utf-8", newline="") as csv_handle,
        ):
            writer = csv.DictWriter(csv_handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                payload = row.to_dict()
                jsonl_handle.write(json.dumps(payload))
                jsonl_handle.write("\n")
                writer.writerow({field: _csv_value(payload.get(field, "")) for field in fieldnames})
