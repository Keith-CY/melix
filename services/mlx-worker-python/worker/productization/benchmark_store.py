from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from worker.productization.apple_silicon_telemetry import AppleSiliconTelemetryCollector
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
from worker.productization.run_evidence import (
    assert_valid_run_evidence_payload,
    build_serving_benchmark_run_evidence,
    monotonic_ms,
)
from worker.productization.run_records import (
    attach_run_record_write_probe,
    build_benchmark_matrix_run_record,
    build_serving_benchmark_run_record,
    write_run_record,
)


class BenchmarkStore:
    def __init__(self, *, telemetry_collector: Any | None = None) -> None:
        self._telemetry_collector = telemetry_collector or AppleSiliconTelemetryCollector()

    def start_telemetry_session(self, *, run_id: str):
        return self._telemetry_collector.start_session(run_id=run_id)

    def persist_serving_benchmark(
        self,
        *,
        jobs_root: Path,
        job: ServingBenchmarkJob,
        results: tuple[ServingBenchmarkResult, ...],
        context_rows: Iterable[dict[str, object]] = (),
        batch_rows: Iterable[dict[str, object]] = (),
        telemetry_collection: Any | None = None,
    ) -> dict[str, Path]:
        artifact_write_started_at_monotonic_ms = monotonic_ms()
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

        context_rows_tuple = tuple(context_rows)
        if context_rows_tuple:
            context_rows_path = jobs_root / "bench-context-rows.jsonl"
            self._write_jsonl(context_rows_path, context_rows_tuple)
            persisted["context_rows_jsonl"] = context_rows_path

        batch_rows_tuple = tuple(batch_rows)
        if batch_rows_tuple:
            batch_rows_path = jobs_root / "bench-batch-rows.jsonl"
            self._write_jsonl(batch_rows_path, batch_rows_tuple)
            persisted["batch_rows_jsonl"] = batch_rows_path

        if telemetry_collection is None:
            telemetry_collection = self._telemetry_collector.collect_completed_run(
                artifact_root=jobs_root,
                run_id=job.job_id,
                output_token_count=self._output_token_count(context_rows_tuple, batch_rows_tuple),
            )
        persisted["telemetry_jsonl"] = Path(telemetry_collection.artifact_path)

        evidence_path = jobs_root / "run-evidence.json"
        evidence = build_serving_benchmark_run_evidence(
            job=job,
            results=results,
            artifact_root=jobs_root,
            artifact_paths=persisted,
            artifact_write_started_at_monotonic_ms=artifact_write_started_at_monotonic_ms,
            artifact_write_duration_ms=monotonic_ms() - artifact_write_started_at_monotonic_ms,
            context_rows=context_rows_tuple,
            batch_rows=batch_rows_tuple,
            telemetry_summary=telemetry_collection.summary,
            telemetry_probes=telemetry_collection.probes,
        )
        evidence_payload = evidence.to_dict()
        assert_valid_run_evidence_payload(evidence_payload)
        evidence_path.write_text(
            json.dumps(evidence_payload, indent=2) + "\n",
            encoding="utf-8",
        )
        persisted["evidence"] = evidence_path

        record_started_at_monotonic_ms = monotonic_ms()
        record_path = jobs_root / "run-record.json"
        record_paths = {**persisted, "run_record": record_path}
        record = build_serving_benchmark_run_record(
            job=job,
            results=results,
            artifact_root=jobs_root,
            artifact_paths=record_paths,
        )
        write_run_record(
            record_path,
            attach_run_record_write_probe(
                record,
                duration_ms=monotonic_ms() - record_started_at_monotonic_ms,
            ),
        )
        persisted["run_record"] = record_path

        return persisted

    @staticmethod
    def _write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            write = handle.write
            dump_json = json.dumps
            for row in rows:
                write(dump_json(row) + "\n")

    @staticmethod
    def _output_token_count(
        context_rows: tuple[dict[str, object], ...],
        batch_rows: tuple[dict[str, object], ...],
    ) -> int:
        total = 0
        for row in (*context_rows, *batch_rows):
            try:
                total += int(row.get("generation_length", 0) or 0)
            except (TypeError, ValueError):
                continue
        return total

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

        persisted = {
            "job": job_path,
            "summary_jsonl": summary_jsonl_path,
            "summary_csv": summary_csv_path,
            "requests_jsonl": requests_jsonl_path,
            "requests_csv": requests_csv_path,
        }
        record_started_at_monotonic_ms = monotonic_ms()
        record_path = jobs_root / "run-record.json"
        record_paths = {**persisted, "run_record": record_path}
        record = build_benchmark_matrix_run_record(
            job=job,
            summary_rows=summary_rows,
            artifact_root=jobs_root,
            artifact_paths=record_paths,
        )
        write_run_record(
            record_path,
            attach_run_record_write_probe(
                record,
                duration_ms=monotonic_ms() - record_started_at_monotonic_ms,
            ),
        )
        persisted["run_record"] = record_path
        return persisted

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
            csv_writer = csv.writer(csv_handle)
            csv_writer.writerow(fieldnames)
            write_jsonl = jsonl_handle.write
            dump_json = json.dumps
            normalize_csv_value = _csv_value
            def csv_rows() -> Iterable[list[str]]:
                for row in rows:
                    payload = row.to_dict()
                    write_jsonl(dump_json(payload) + "\n")
                    payload_get = payload.get
                    yield [normalize_csv_value(payload_get(field, "")) for field in fieldnames]

            csv_writer.writerows(csv_rows())
