from __future__ import annotations

import json
from pathlib import Path

from worker.productization.evaluation_schemas import EvaluationJob, EvaluationResult, EvaluationSample


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
    def _samples_csv(samples: tuple[EvaluationSample, ...]) -> str:
        header = [
            "id",
            "correct",
            "expected",
            "predicted",
            "question",
            "raw_response",
            "time_s",
            "parse_status",
        ]
        rows = [",".join(header)]
        for sample in samples:
            rows.append(
                ",".join(
                    [
                        EvaluationStore._csv_field(sample.sample_id),
                        "true" if sample.correct else "false",
                        EvaluationStore._csv_field(sample.expected),
                        EvaluationStore._csv_field(sample.predicted),
                        EvaluationStore._csv_field(sample.question),
                        EvaluationStore._csv_field(sample.raw_response),
                        EvaluationStore._csv_field(str(sample.time_s)),
                        EvaluationStore._csv_field(sample.parse_status),
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
