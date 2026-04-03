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

        persisted: dict[str, Path] = {"job": job_path, "result": result_path}
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
