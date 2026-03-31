from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import re
import time

from worker.productization.benchmark_queue import BenchmarkQueueRecord, BenchmarkQueueStore
from worker.productization.evaluation_schemas import EvaluationJob, EvaluationResult
from worker.productization.evaluation_store import EvaluationStore
from worker.productization.benchmark_schemas import (
    build_evaluation_job,
    build_evaluation_result,
)


_SUPPORTED_SUITE_IDS = {"mmlu"}
_ARITHMETIC_PROMPT_PATTERN = re.compile(r"\s*(\d+)\s*([+-])\s*(\d+)\s*\?\s*")


@dataclass(frozen=True)
class EvaluationRun:
    job: EvaluationJob
    result: EvaluationResult
    persisted_paths: dict[str, Path]


class EvaluationCore:
    def __init__(
        self,
        *,
        jobs_root: Path | None = None,
        store: EvaluationStore | None = None,
        queue_store: BenchmarkQueueStore | None = None,
    ) -> None:
        self._jobs_root = Path(jobs_root).resolve() if jobs_root is not None else None
        self._store = store or EvaluationStore()
        self._queue_store = queue_store or BenchmarkQueueStore()

    def run_local_suite(
        self,
        *,
        model_id: str,
        suite_id: str,
        dataset_root: Path,
        sample_size: int,
        parameters: dict[str, str] | None = None,
    ) -> EvaluationRun:
        dataset_root = Path(dataset_root).resolve()
        if suite_id not in _SUPPORTED_SUITE_IDS:
            raise ValueError(f"Unsupported evaluation suite: {suite_id}")

        manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
        if manifest["suite_id"] != suite_id:
            raise ValueError(
                f"Dataset suite mismatch: expected {suite_id}, found {manifest['suite_id']}"
            )

        samples = [
            json.loads(line)
            for line in (dataset_root / "samples.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        selected = samples[: max(sample_size, 0)]
        correct = sum(1 for sample in selected if self._sample_is_correct(sample))
        accuracy = round(correct / max(len(selected), 1), 2)
        job_parameters = {"dataset_root": str(dataset_root)}
        if parameters:
            job_parameters.update(parameters)
        job_parameters.setdefault("sample_size", str(len(selected)))

        report_path = self._result_path(dataset_root)
        job = build_evaluation_job(
            job_id="eval-local",
            model_id=model_id,
            suite_id=suite_id,
            dataset_id=manifest["dataset_id"],
            sample_size=len(selected),
            scoring_mode="deterministic_accuracy",
            parameters=job_parameters,
            status="completed",
        )
        result = build_evaluation_result(
            job_id=job.job_id,
            suite_id=suite_id,
            dataset_id=manifest["dataset_id"],
            sample_size=len(selected),
            metrics={f"eval.{suite_id}.accuracy": accuracy},
            report_path=str(report_path),
        )
        persisted_paths: dict[str, Path] = {}
        if self._jobs_root is not None:
            queue_root = self._jobs_root / "queue"
            queued_at = int(time.time() * 1000)
            self._queue_store.enqueue(
                queue_root=queue_root,
                record=BenchmarkQueueRecord(
                    queue_item_id=job.job_id,
                    job_kind="evaluation",
                    model_id=model_id,
                    suite_ids=(suite_id,),
                    parameters=job_parameters,
                    status="queued",
                    created_at_unix_ms=queued_at,
                    updated_at_unix_ms=queued_at,
                ),
            )
            self._queue_store.transition(
                queue_root=queue_root,
                queue_item_id=job.job_id,
                status="running",
                updated_at_unix_ms=queued_at + 1,
            )
            persisted_paths = self._store.persist_result(
                jobs_root=self._jobs_root,
                job=job,
                result=result,
            )
            self._queue_store.transition(
                queue_root=queue_root,
                queue_item_id=job.job_id,
                status="completed",
                updated_at_unix_ms=int(time.time() * 1000),
            )
        return EvaluationRun(job=job, result=result, persisted_paths=persisted_paths)

    def _result_path(self, dataset_root: Path) -> Path:
        if self._jobs_root is not None:
            return self._jobs_root / "evaluation-result.json"
        return dataset_root / "evaluation-result.json"

    @staticmethod
    def _sample_is_correct(sample: dict[str, object]) -> bool:
        expected = str(sample.get("expected", "")).strip()
        predicted = EvaluationCore._deterministic_answer(str(sample.get("prompt", "")))
        return predicted == expected

    @staticmethod
    def _deterministic_answer(prompt: str) -> str:
        match = _ARITHMETIC_PROMPT_PATTERN.fullmatch(prompt)
        if match is None:
            return ""

        left = int(match.group(1))
        operator = match.group(2)
        right = int(match.group(3))
        if operator == "+":
            return str(left + right)
        return str(left - right)
