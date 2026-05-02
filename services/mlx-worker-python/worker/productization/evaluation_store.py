from __future__ import annotations

from collections.abc import Iterable
import json
from pathlib import Path

from worker.productization.evaluation_reports import build_evaluation_compare_report_markdown
from worker.productization.evaluation_schemas import (
    EvaluationCompareJob,
    EvaluationCompareSample,
    EvaluationCompareSummary,
    EvaluationJob,
    EvaluationResult,
    EvaluationSample,
)


class EvaluationStore:
    def persist_result(
        self,
        *,
        jobs_root: Path,
        job: EvaluationJob,
        result: EvaluationResult,
        samples: tuple[EvaluationSample, ...] = (),
    ) -> dict[str, Path]:
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
        if samples:
            jsonl_path = run_root / "evaluation-samples.jsonl"
            self._write_jsonl(jsonl_path, (sample.to_dict() for sample in samples))
            csv_path = run_root / "evaluation-samples.csv"
            self._write_samples_csv(csv_path, samples)
            persisted["samples_jsonl"] = jsonl_path
            persisted["samples_csv"] = csv_path
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
        summary_csv_path.write_text(
            self._compare_summary_csv(job=job, summaries=summaries),
            encoding="utf-8",
        )

        samples_jsonl_path = run_root / "evaluation-compare-samples.jsonl"
        self._write_jsonl(samples_jsonl_path, (sample.to_dict() for sample in samples))

        report_markdown_path = run_root / "evaluation-compare-report.md"
        report_markdown_path.write_text(
            build_evaluation_compare_report_markdown(job=job, summaries=summaries),
            encoding="utf-8",
        )

        return {
            "job": job_path,
            "summary_json": summary_json_path,
            "summary_csv": summary_csv_path,
            "samples_jsonl": samples_jsonl_path,
            "report_markdown": report_markdown_path,
        }

    @staticmethod
    def _write_jsonl(path: Path, rows: Iterable[object]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row))
                handle.write("\n")

    @staticmethod
    def _write_samples_csv(path: Path, samples: tuple[EvaluationSample, ...]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            handle.write(",".join(EvaluationStore._samples_csv_header()))
            handle.write("\n")
            for sample in samples:
                handle.write(EvaluationStore._sample_csv_row(sample))
                handle.write("\n")

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
        return {
            "schema_version": "melix.evaluation_compare_summary_bundle.v1",
            "job_id": job.job_id,
            "base_model_id": job.base_model_id,
            "suite_id": job.suite_id,
            "dataset_id": job.dataset_id,
            "sample_size": job.sample_size,
            "created_at_unix_ms": job.created_at_unix_ms,
            "target_summaries": [summary.to_dict() for summary in summaries],
        }

    @staticmethod
    def _compare_summary_csv(
        *,
        job: EvaluationCompareJob,
        summaries: tuple[EvaluationCompareSummary, ...],
    ) -> str:
        # Module 2 adds two trailing columns carrying adapter lineage. New
        # columns land at the end of the header row so downstream parsers
        # keyed on column order preserve their existing behavior for the
        # first 21 columns; the two new columns are empty for registered
        # (non-adapter) targets.
        header = [
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
        # Index lineage entries by target_model_id for O(1) lookup during
        # row emission. Targets without a lineage record (legacy jobs or
        # registered models) get empty-string adapter columns.
        lineage_by_target_id = {entry.target_model_id: entry for entry in job.target_lineage}
        rows = [",".join(header)]
        for summary in summaries:
            bootstrap_interval = summary.statistical_evidence.get("bootstrap", {})
            analytical_interval = summary.statistical_evidence.get("analytical", {})
            lineage = lineage_by_target_id.get(summary.target_model_id)
            rows.append(
                ",".join(
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
            )
        return "\n".join(rows) + "\n"

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
        ]

    @staticmethod
    def _sample_csv_row(sample: EvaluationSample) -> str:
        return ",".join(
            [
                EvaluationStore._csv_field(sample.sample_id),
                EvaluationStore._csv_field(sample.task_kind),
                EvaluationStore._csv_field(sample.target),
                EvaluationStore._csv_field(sample.extracted_result),
                EvaluationStore._csv_field(sample.input_text),
                EvaluationStore._csv_field(sample.raw_response),
                EvaluationStore._csv_field(str(sample.typed_score)),
                EvaluationStore._csv_field(str(sample.time_s)),
                EvaluationStore._csv_field(sample.extraction_status),
                EvaluationStore._csv_field(sample.validation_status),
                EvaluationStore._csv_field(sample.failure_reason),
                EvaluationStore._csv_field(",".join(sample.input_modalities)),
                EvaluationStore._csv_field(",".join(sample.media_references)),
                EvaluationStore._csv_field(sample.code_language),
                EvaluationStore._csv_field(sample.code_entry_point),
                EvaluationStore._csv_field(sample.code_compile_status),
                EvaluationStore._csv_field(sample.code_runtime_status),
                EvaluationStore._csv_field(sample.code_timeout_status),
                EvaluationStore._csv_field(sample.code_test_status),
                EvaluationStore._csv_field(str(sample.code_tests_passed)),
                EvaluationStore._csv_field(str(sample.code_tests_total)),
                EvaluationStore._csv_field(sample.code_failure_detail),
                EvaluationStore._csv_field(sample.category_label),
                EvaluationStore._csv_field(sample.subject_label),
                EvaluationStore._csv_field(str(sample.sample_render_ms)),
                EvaluationStore._csv_field(str(sample.inference_ms)),
                EvaluationStore._csv_field(str(sample.extraction_ms)),
                EvaluationStore._csv_field(str(sample.validation_ms)),
                EvaluationStore._csv_field(str(sample.scoring_ms)),
                EvaluationStore._csv_field(str(sample.raw_response_chars)),
                EvaluationStore._csv_field(str(sample.extracted_result_chars)),
                EvaluationStore._csv_field(sample.failure_stage),
            ]
        )

    @staticmethod
    def _csv_field(value: str) -> str:
        escaped = value.replace("\"", "\"\"")
        if "," in escaped or "\n" in escaped or "\"" in escaped:
            return f"\"{escaped}\""
        return escaped
