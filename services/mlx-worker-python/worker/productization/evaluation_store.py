from __future__ import annotations

from collections.abc import Iterable
import json
from pathlib import Path
from typing import Any

from worker.productization.apple_silicon_telemetry import (
    AppleSiliconTelemetryCollector,
    NoOpAppleSiliconTelemetryCollector,
)
from worker.productization.evaluation_reports import build_evaluation_compare_report_markdown
from worker.productization.evaluation_schemas import (
    EvaluationCompareJob,
    EvaluationCompareSample,
    EvaluationCompareSummary,
    EvaluationJob,
    EvaluationResult,
    EvaluationSample,
)
from worker.productization.probe_policy import ProbePolicy
from worker.productization.run_evidence import (
    assert_valid_run_evidence_payload,
    build_evaluation_run_evidence,
    monotonic_ms,
)
from worker.productization.run_records import (
    attach_run_record_write_probe,
    build_evaluation_compare_statistical_verdict,
    build_evaluation_compare_run_record,
    build_evaluation_run_record,
    object_payload,
    write_run_record,
)


class EvaluationStore:
    def __init__(
        self,
        *,
        telemetry_collector: Any | None = None,
        probe_policy: ProbePolicy | None = None,
    ) -> None:
        self._probe_policy = probe_policy or ProbePolicy.from_env()
        self._telemetry_collector = telemetry_collector or self._default_telemetry_collector(
            self._probe_policy
        )

    def start_telemetry_session(self, *, run_id: str):
        return self._telemetry_collector.start_session(run_id=run_id)

    @staticmethod
    def _default_telemetry_collector(policy: ProbePolicy) -> Any:
        if policy.telemetry_enabled:
            return AppleSiliconTelemetryCollector()
        return NoOpAppleSiliconTelemetryCollector(reason=policy.no_op_reason)

    def persist_result(
        self,
        *,
        jobs_root: Path,
        job: EvaluationJob,
        result: EvaluationResult,
        samples: tuple[EvaluationSample, ...] = (),
        telemetry_collection: Any | None = None,
        model_memory_summary: dict[str, object] | None = None,
        extra_artifact_paths: dict[str, Path] | None = None,
    ) -> dict[str, Path]:
        artifact_write_started_at_monotonic_ms = monotonic_ms()
        run_root = Path(job.output_dir) if job.output_dir else jobs_root
        run_root.mkdir(parents=True, exist_ok=True)

        job_path = run_root / "evaluation-job.json"
        job_path.write_text(
            json.dumps(job.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )

        result_path = run_root / "evaluation-result.json"
        result_path.write_text(
            json.dumps(result.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )

        summary_path = run_root / "evaluation-summary.json"
        summary_path.write_text(
            json.dumps(self._summary_payload(job=job, result=result), indent=2) + "\n",
            encoding="utf-8",
        )

        summary_csv_path = run_root / "evaluation-summary.csv"
        summary_csv_path.write_text(
            self._summary_csv(job=job, result=result),
            encoding="utf-8",
        )

        persisted: dict[str, Path] = {
            "job": job_path,
            "result": result_path,
            "summary_json": summary_path,
            "summary_csv": summary_csv_path,
        }
        if extra_artifact_paths:
            # Include extension artifacts before evidence generation so their roles appear in run-evidence.
            persisted.update(extra_artifact_paths)
        if samples:
            jsonl_path = run_root / "evaluation-samples.jsonl"
            self._write_jsonl(jsonl_path, (sample.to_dict() for sample in samples))
            csv_path = run_root / "evaluation-samples.csv"
            self._write_samples_csv(csv_path, samples)
            persisted["samples_jsonl"] = jsonl_path
            persisted["samples_csv"] = csv_path
        if telemetry_collection is None:
            telemetry_collection = self._telemetry_collector.collect_completed_run(
                artifact_root=run_root,
                run_id=job.job_id,
            )
        persisted["telemetry_jsonl"] = Path(telemetry_collection.artifact_path)
        evidence_path = run_root / "run-evidence.json"
        evidence = build_evaluation_run_evidence(
            job=job,
            result=result,
            sample_count=len(samples) if samples else result.sample_size,
            artifact_root=run_root,
            artifact_paths=persisted,
            artifact_write_started_at_monotonic_ms=artifact_write_started_at_monotonic_ms,
            artifact_write_duration_ms=monotonic_ms() - artifact_write_started_at_monotonic_ms,
            samples=samples,
            telemetry_summary=telemetry_collection.summary,
            telemetry_probes=telemetry_collection.probes,
            model_memory_summary=model_memory_summary,
        )
        evidence_payload = evidence.to_dict()
        assert_valid_run_evidence_payload(evidence_payload)
        evidence_path.write_text(
            json.dumps(evidence_payload, indent=2) + "\n",
            encoding="utf-8",
        )
        persisted["evidence"] = evidence_path
        record_started_at_monotonic_ms = monotonic_ms()
        record_path = run_root / "run-record.json"
        record_paths = {**persisted, "run_record": record_path}
        record = build_evaluation_run_record(
            job=job,
            result=result,
            artifact_root=run_root,
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

    def persist_compare_result(
        self,
        *,
        jobs_root: Path,
        job: EvaluationCompareJob,
        summaries: tuple[EvaluationCompareSummary, ...],
        samples: tuple[EvaluationCompareSample, ...] = (),
    ) -> dict[str, Path]:
        run_root = Path(job.output_dir) if job.output_dir else jobs_root
        run_root.mkdir(parents=True, exist_ok=True)

        job_path = run_root / "evaluation-compare-job.json"
        job_path.write_text(
            json.dumps(job.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )

        summary_payload = self._compare_summary_payload(job=job, summaries=summaries)
        summary_json_path = run_root / "evaluation-compare-summary.json"
        summary_json_path.write_text(
            json.dumps(summary_payload, indent=2) + "\n",
            encoding="utf-8",
        )

        summary_csv_path = run_root / "evaluation-compare-summary.csv"
        self._write_compare_summary_csv(summary_csv_path, job=job, summaries=summaries)

        samples_jsonl_path = run_root / "evaluation-compare-samples.jsonl"
        self._write_jsonl(samples_jsonl_path, (sample.to_dict() for sample in samples))

        report_markdown_path = run_root / "evaluation-compare-report.md"
        report_markdown_path.write_text(
            build_evaluation_compare_report_markdown(job=job, summaries=summaries),
            encoding="utf-8",
        )

        persisted = {
            "job": job_path,
            "summary_json": summary_json_path,
            "summary_csv": summary_csv_path,
            "samples_jsonl": samples_jsonl_path,
            "report_markdown": report_markdown_path,
        }
        record_started_at_monotonic_ms = monotonic_ms()
        record_path = run_root / "run-record.json"
        record_paths = {**persisted, "run_record": record_path}
        record = build_evaluation_compare_run_record(
            job=job,
            summaries=summaries,
            artifact_root=run_root,
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
    def _write_jsonl(path: Path, rows: Iterable[object]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            write = handle.write
            dumps = json.dumps
            for row in rows:
                write(dumps(row) + "\n")

    @staticmethod
    def _write_samples_csv(path: Path, samples: tuple[EvaluationSample, ...]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            write = handle.write
            sample_csv_row = EvaluationStore._sample_csv_row
            write(",".join(EvaluationStore._samples_csv_header()) + "\n")
            for sample in samples:
                write(sample_csv_row(sample) + "\n")

    @staticmethod
    def _write_compare_summary_csv(
        path: Path,
        *,
        job: EvaluationCompareJob,
        summaries: tuple[EvaluationCompareSummary, ...],
    ) -> None:
        lineage_by_target_id = {entry.target_model_id: entry for entry in job.target_lineage}
        with path.open("w", encoding="utf-8") as handle:
            write = handle.write
            compare_summary_csv_row = EvaluationStore._compare_summary_csv_row
            write(",".join(EvaluationStore._compare_summary_csv_header()) + "\n")
            for summary in summaries:
                write(compare_summary_csv_row(job=job, summary=summary, lineage_by_target_id=lineage_by_target_id) + "\n")

    @staticmethod
    def _summary_payload(*, job: EvaluationJob, result: EvaluationResult) -> dict[str, object]:
        return {
            "schema_version": result.schema_version,
            "job_id": job.job_id,
            "task_kind": job.task_kind,
            "source_repo": job.source_repo,
            "model_id": job.model_id,
            "suite_id": job.suite_id,
            "dataset_id": job.dataset_id,
            "primary_score_name": result.primary_score_name,
            "primary_score_value": result.primary_score_value,
            "sample_size": result.sample_size,
            "extraction_success_count": result.extraction_success_count,
            "validation_success_count": result.validation_success_count,
            "scored_sample_count": result.scored_sample_count,
            "failure_count": result.failure_count,
            "duration_seconds": result.duration_seconds,
            "created_at_unix_ms": job.created_at_unix_ms,
        }

    @staticmethod
    def _summary_csv(*, job: EvaluationJob, result: EvaluationResult) -> str:
        header = [
            "job_id",
            "task_kind",
            "source_repo",
            "model_id",
            "suite_id",
            "dataset_id",
            "primary_score_name",
            "primary_score_value",
            "sample_size",
            "extraction_success_count",
            "validation_success_count",
            "scored_sample_count",
            "failure_count",
            "duration_seconds",
            "created_at_unix_ms",
        ]
        row = EvaluationStore._summary_payload(job=job, result=result)
        rows = [",".join(header)]
        rows.append(
            ",".join(
                [
                    EvaluationStore._csv_field(str(row["job_id"])),
                    EvaluationStore._csv_field(str(row["task_kind"])),
                    EvaluationStore._csv_field(str(row["source_repo"])),
                    EvaluationStore._csv_field(str(row["model_id"])),
                    EvaluationStore._csv_field(str(row["suite_id"])),
                    EvaluationStore._csv_field(str(row["dataset_id"])),
                    EvaluationStore._csv_field(str(row["primary_score_name"])),
                    EvaluationStore._csv_field(str(row["primary_score_value"])),
                    EvaluationStore._csv_field(str(row["sample_size"])),
                    EvaluationStore._csv_field(str(row["extraction_success_count"])),
                    EvaluationStore._csv_field(str(row["validation_success_count"])),
                    EvaluationStore._csv_field(str(row["scored_sample_count"])),
                    EvaluationStore._csv_field(str(row["failure_count"])),
                    EvaluationStore._csv_field(str(row["duration_seconds"])),
                    EvaluationStore._csv_field(str(row["created_at_unix_ms"])),
                ]
            )
        )
        return "\n".join(rows) + "\n"

    @staticmethod
    def _compare_summary_payload(
        *,
        job: EvaluationCompareJob,
        summaries: tuple[EvaluationCompareSummary, ...],
    ) -> dict[str, object]:
        dataset_lineage = object_payload(getattr(job, "dataset_lineage", None))
        return {
            "schema_version": "melix.evaluation_compare_summary_bundle.v1",
            "job_id": job.job_id,
            "base_model_id": job.base_model_id,
            "suite_id": job.suite_id,
            "dataset_id": job.dataset_id,
            "sample_size": job.sample_size,
            "created_at_unix_ms": job.created_at_unix_ms,
            "dataset_lineage": dataset_lineage,
            "target_lineage": [entry.to_dict() for entry in job.target_lineage],
            "statistical_verdicts": [
                build_evaluation_compare_statistical_verdict(summary) for summary in summaries
            ],
            "target_summaries": [summary.to_dict() for summary in summaries],
        }

    @staticmethod
    def _compare_summary_csv(
        *,
        job: EvaluationCompareJob,
        summaries: tuple[EvaluationCompareSummary, ...],
    ) -> str:
        lineage_by_target_id = {entry.target_model_id: entry for entry in job.target_lineage}
        rows = [",".join(EvaluationStore._compare_summary_csv_header())]
        for summary in summaries:
            rows.append(
                EvaluationStore._compare_summary_csv_row(
                    job=job,
                    summary=summary,
                    lineage_by_target_id=lineage_by_target_id,
                )
            )
        return "\n".join(rows) + "\n"

    @staticmethod
    def _compare_summary_csv_header() -> list[str]:
        # Module 2 adds two trailing columns carrying adapter lineage. New
        # columns land at the end of the header row so downstream parsers
        # keyed on column order preserve their existing behavior for the
        # first 21 columns; the two new columns are empty for registered
        # (non-adapter) targets.
        return [
            "job_id",
            "base_model_id",
            "target_model_id",
            "suite_id",
            "dataset_id",
            "sample_size",
            "win_count",
            "loss_count",
            "tie_count",
            "regression_count",
            "base_accuracy",
            "target_accuracy",
            "delta_accuracy",
            "effect_threshold",
            "verdict",
            "bootstrap_lower_bound",
            "bootstrap_upper_bound",
            "analytical_lower_bound",
            "analytical_upper_bound",
            "duration_seconds",
            "created_at_unix_ms",
            "target_adapter_manifest_path",
            "target_adapter_set_hash",
        ]

    @staticmethod
    def _compare_summary_csv_row(
        *,
        job: EvaluationCompareJob,
        summary: EvaluationCompareSummary,
        lineage_by_target_id: dict[str, object] | None = None,
    ) -> str:
        bootstrap_interval = summary.statistical_evidence.get("bootstrap", {})
        analytical_interval = summary.statistical_evidence.get("analytical", {})
        if lineage_by_target_id is None:
            lineage_by_target_id = {entry.target_model_id: entry for entry in job.target_lineage}
        lineage = lineage_by_target_id.get(summary.target_model_id)
        return ",".join(
            [
                EvaluationStore._csv_field(job.job_id),
                EvaluationStore._csv_field(job.base_model_id),
                EvaluationStore._csv_field(summary.target_model_id),
                EvaluationStore._csv_field(job.suite_id),
                EvaluationStore._csv_field(job.dataset_id),
                EvaluationStore._csv_field(str(job.sample_size)),
                EvaluationStore._csv_field(str(summary.win_count)),
                EvaluationStore._csv_field(str(summary.loss_count)),
                EvaluationStore._csv_field(str(summary.tie_count)),
                EvaluationStore._csv_field(str(summary.regression_count)),
                EvaluationStore._csv_field(str(summary.base_accuracy)),
                EvaluationStore._csv_field(str(summary.target_accuracy)),
                EvaluationStore._csv_field(str(summary.delta_accuracy)),
                EvaluationStore._csv_field(str(summary.effect_threshold)),
                EvaluationStore._csv_field(summary.verdict),
                EvaluationStore._csv_field(str(bootstrap_interval.get("lower_bound", ""))),
                EvaluationStore._csv_field(str(bootstrap_interval.get("upper_bound", ""))),
                EvaluationStore._csv_field(str(analytical_interval.get("lower_bound", ""))),
                EvaluationStore._csv_field(str(analytical_interval.get("upper_bound", ""))),
                EvaluationStore._csv_field(str(summary.duration_seconds)),
                EvaluationStore._csv_field(str(job.created_at_unix_ms)),
                EvaluationStore._csv_field(lineage.adapter_manifest_path if lineage else ""),
                EvaluationStore._csv_field(lineage.adapter_set_hash if lineage else ""),
            ]
        )

    @staticmethod
    def _samples_csv(samples: tuple[EvaluationSample, ...]) -> str:
        rows = [",".join(EvaluationStore._samples_csv_header())]
        for sample in samples:
            rows.append(EvaluationStore._sample_csv_row(sample))
        return "\n".join(rows) + "\n"

    @staticmethod
    def _samples_csv_header() -> list[str]:
        return [
            "id",
            "task_kind",
            "target",
            "extracted_result",
            "input_text",
            "raw_response",
            "typed_score",
            "time_s",
            "extraction_status",
            "validation_status",
            "failure_reason",
            "input_modalities",
            "media_references",
            "code_language",
            "code_entry_point",
            "code_compile_status",
            "code_runtime_status",
            "code_timeout_status",
            "code_test_status",
            "code_tests_passed",
            "code_tests_total",
            "code_failure_detail",
            "category_label",
            "subject_label",
            "sample_render_ms",
            "inference_ms",
            "extraction_ms",
            "validation_ms",
            "scoring_ms",
            "raw_response_chars",
            "extracted_result_chars",
            "failure_stage",
            "final_answer",
            "parse_status",
        ]

    @staticmethod
    def _sample_csv_row(sample: EvaluationSample) -> str:
        csv_field = EvaluationStore._csv_field
        return ",".join(
            [
                csv_field(sample.sample_id),
                csv_field(sample.task_kind),
                csv_field(sample.target),
                csv_field(sample.extracted_result),
                csv_field(sample.input_text),
                csv_field(sample.raw_response),
                str(sample.typed_score),
                str(sample.time_s),
                csv_field(sample.extraction_status),
                csv_field(sample.validation_status),
                csv_field(sample.failure_reason),
                csv_field(",".join(sample.input_modalities)),
                csv_field(",".join(sample.media_references)),
                csv_field(sample.code_language),
                csv_field(sample.code_entry_point),
                csv_field(sample.code_compile_status),
                csv_field(sample.code_runtime_status),
                csv_field(sample.code_timeout_status),
                csv_field(sample.code_test_status),
                str(sample.code_tests_passed),
                str(sample.code_tests_total),
                csv_field(sample.code_failure_detail),
                csv_field(sample.category_label),
                csv_field(sample.subject_label),
                str(sample.sample_render_ms),
                str(sample.inference_ms),
                str(sample.extraction_ms),
                str(sample.validation_ms),
                str(sample.scoring_ms),
                str(sample.raw_response_chars),
                str(sample.extracted_result_chars),
                csv_field(sample.failure_stage),
                csv_field(sample.final_answer),
                csv_field(sample.parse_status),
            ]
        )

    @staticmethod
    def _csv_field(value: str) -> str:
        if "," not in value and "\n" not in value and "\"" not in value:
            return value
        return '"' + value.replace('"', '""') + '"'
