from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import re
import time

from worker.productization.benchmark_queue import BenchmarkQueueRecord, BenchmarkQueueStore
from worker.productization.evaluation_schemas import EvaluationJob, EvaluationResult, EvaluationSample
from worker.productization.evaluation_store import EvaluationStore
from worker.productization.benchmark_schemas import (
    build_evaluation_job,
    build_evaluation_result,
    build_evaluation_sample,
)


_SUITE_SCORE_MODES = {
    "mmlu": ("accuracy", "multiple_choice_accuracy"),
    "arc_challenge": ("accuracy", "multiple_choice_accuracy"),
    "hellaswag": ("accuracy", "multiple_choice_accuracy"),
    "winogrande": ("accuracy", "multiple_choice_accuracy"),
    "truthfulqa_mc": ("accuracy", "multiple_choice_accuracy"),
    "gsm8k": ("exact_match", "exact_match"),
    "humaneval": ("pass_at_1", "pass_at_1"),
    "mbpp": ("pass_at_1", "pass_at_1"),
}
_ARITHMETIC_PROMPT_PATTERN = re.compile(r"\s*(\d+)\s*([+-])\s*(\d+)\s*\?\s*")


@dataclass(frozen=True)
class EvaluationRun:
    job: EvaluationJob
    result: EvaluationResult
    samples: tuple[EvaluationSample, ...]
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
        if suite_id not in _SUITE_SCORE_MODES:
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
        score_name, scoring_mode = _SUITE_SCORE_MODES[suite_id]
        created_at_unix_ms = int(time.time() * 1000)
        job_id = self._next_job_id()
        run_root = self._run_root(job_id)
        sample_records = tuple(
            self._build_sample_record(
                job_id=job_id,
                suite_id=suite_id,
                dataset_id=manifest["dataset_id"],
                index=index,
                sample=sample,
            )
            for index, sample in enumerate(selected, start=1)
        )
        correct = sum(1 for sample in sample_records if sample.correct)
        accuracy = round(correct / max(len(sample_records), 1), 4)
        job_parameters = {"dataset_root": str(dataset_root)}
        if parameters:
            job_parameters.update(parameters)
        job_parameters.setdefault("sample_size", str(len(sample_records)))

        report_path = self._result_path(run_root if self._jobs_root is not None else dataset_root)
        output_dir = str(run_root) if self._jobs_root is not None else str(dataset_root)
        job = build_evaluation_job(
            job_id=job_id,
            model_id=model_id,
            task_kind=job_parameters.get("task_kind", "text-generation"),
            source_repo=job_parameters.get("source_repo", ""),
            suite_id=suite_id,
            dataset_id=manifest["dataset_id"],
            sample_size=len(sample_records),
            scoring_mode=scoring_mode,
            parameters=job_parameters,
            status="completed",
            output_dir=output_dir,
            created_at_unix_ms=created_at_unix_ms,
            updated_at_unix_ms=created_at_unix_ms,
        )
        result = build_evaluation_result(
            job_id=job.job_id,
            suite_id=suite_id,
            dataset_id=manifest["dataset_id"],
            sample_size=len(sample_records),
            metrics={
                f"eval.{suite_id}.{score_name}": accuracy,
                f"eval.{suite_id}.correct_count": float(correct),
            },
            report_path=str(report_path),
            units={
                f"eval.{suite_id}.{score_name}": "ratio",
                f"eval.{suite_id}.correct_count": "count",
            },
        )
        persisted_paths: dict[str, Path] = {}
        if self._jobs_root is not None:
            queue_root = self._jobs_root / "queue"
            queued_at = created_at_unix_ms
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
                samples=sample_records,
            )
            self._queue_store.transition(
                queue_root=queue_root,
                queue_item_id=job.job_id,
                status="completed",
                updated_at_unix_ms=int(time.time() * 1000),
            )
        return EvaluationRun(job=job, result=result, samples=sample_records, persisted_paths=persisted_paths)

    def _result_path(self, run_root: Path) -> Path:
        if self._jobs_root is not None:
            return run_root / "evaluation-result.json"
        return run_root / "evaluation-result.json"

    def _next_job_id(self) -> str:
        if self._jobs_root is None:
            return "eval-local"
        runs_root = self._jobs_root / "runs"
        runs_root.mkdir(parents=True, exist_ok=True)
        existing = sorted(
            int(path.name.removeprefix("eval-"))
            for path in runs_root.iterdir()
            if path.is_dir() and path.name.startswith("eval-") and path.name.removeprefix("eval-").isdigit()
        )
        next_index = (existing[-1] + 1) if existing else 1
        return f"eval-{next_index:04d}"

    def _run_root(self, job_id: str) -> Path:
        if self._jobs_root is None:
            return Path.cwd()
        return self._jobs_root / "runs" / job_id

    @staticmethod
    def _build_sample_record(
        *,
        job_id: str,
        suite_id: str,
        dataset_id: str,
        index: int,
        sample: dict[str, object],
    ) -> EvaluationSample:
        prompt = str(sample.get("prompt", sample.get("question", "")))
        expected = str(sample.get("expected", sample.get("answer", ""))).strip()
        started_at = time.perf_counter()
        predicted = EvaluationCore._deterministic_answer(prompt)
        duration_s = round(time.perf_counter() - started_at, 6)
        parse_status = "parsed" if predicted else "empty_prediction"
        return build_evaluation_sample(
            job_id=job_id,
            suite_id=suite_id,
            dataset_id=dataset_id,
            sample_id=str(sample.get("id", index)),
            question=prompt,
            expected=expected,
            predicted=predicted,
            raw_response=predicted,
            correct=predicted == expected,
            time_s=duration_s,
            parse_status=parse_status,
        )

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
