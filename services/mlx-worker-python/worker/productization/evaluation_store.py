from __future__ import annotations

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
            jsonl_path.write_text(
                "\n".join(json.dumps(sample.to_dict()) for sample in samples) + "\n",
                encoding="utf-8",
            )
            csv_path = run_root / "evaluation-samples.csv"
            csv_path.write_text(
                self._samples_csv(samples),
                encoding="utf-8",
            )
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
        samples_jsonl_path.write_text(
            "\n".join(json.dumps(sample.to_dict()) for sample in samples) + ("\n" if samples else ""),
            encoding="utf-8",
        )

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
    def _summary_payload(*, job: EvaluationJob, result: EvaluationResult) -> dict[str, object]:
        return {
            "schema_version": result.schema_version,
            "job_id": job.job_id,
            "task_kind": job.task_kind,
            "source_repo": job.source_repo,
            "model_id": job.model_id,
            "suite_id": job.suite_id,
            "dataset_id": job.dataset_id,
            "score_name": result.score_name,
            "score_value": result.score_value,
            "sample_size": result.sample_size,
            "correct_count": result.correct_count,
            "incorrect_count": result.incorrect_count,
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
            "score_name",
            "score_value",
            "sample_size",
            "correct_count",
            "incorrect_count",
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
                    EvaluationStore._csv_field(str(row["score_name"])),
                    EvaluationStore._csv_field(str(row["score_value"])),
                    EvaluationStore._csv_field(str(row["sample_size"])),
                    EvaluationStore._csv_field(str(row["correct_count"])),
                    EvaluationStore._csv_field(str(row["incorrect_count"])),
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
        ]
        rows = [",".join(header)]
        for summary in summaries:
            bootstrap_interval = summary.statistical_evidence.get("bootstrap", {})
            analytical_interval = summary.statistical_evidence.get("analytical", {})
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
                    ]
                )
            )
        return "\n".join(rows) + "\n"

    @staticmethod
    def _samples_csv(samples: tuple[EvaluationSample, ...]) -> str:
        header = [
            "id",
            "task_kind",
            "correct",
            "expected",
            "predicted",
            "question",
            "raw_response",
            "time_s",
            "parse_status",
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
        ]
        rows = [",".join(header)]
        for sample in samples:
            rows.append(
                ",".join(
                    [
                        EvaluationStore._csv_field(sample.sample_id),
                        EvaluationStore._csv_field(sample.task_kind),
                        "true" if sample.correct else "false",
                        EvaluationStore._csv_field(sample.expected),
                        EvaluationStore._csv_field(sample.predicted),
                        EvaluationStore._csv_field(sample.question),
                        EvaluationStore._csv_field(sample.raw_response),
                        EvaluationStore._csv_field(str(sample.time_s)),
                        EvaluationStore._csv_field(sample.parse_status),
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
                    ]
                )
            )
        return "\n".join(rows) + "\n"

    @staticmethod
    def _csv_field(value: str) -> str:
        escaped = value.replace("\"", "\"\"")
        if "," in escaped or "\n" in escaped or "\"" in escaped:
            return f"\"{escaped}\""
        return escaped
