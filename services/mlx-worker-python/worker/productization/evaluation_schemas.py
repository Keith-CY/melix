from __future__ import annotations

from dataclasses import dataclass


_EVALUATION_DATASET_PACKAGE_SCHEMA_VERSION = "melix.evaluation_dataset_package.v1"
_EVALUATION_JOB_SCHEMA_VERSION = "melix.evaluation_job.v1"
_EVALUATION_RESULT_SCHEMA_VERSION = "melix.evaluation_result.v1"
_EVALUATION_SAMPLE_SCHEMA_VERSION = "melix.evaluation_sample.v1"


@dataclass(frozen=True)
class EvaluationDatasetPackageManifest:
    schema_version: str
    dataset_id: str
    suite_id: str
    version: str
    sample_count: int
    split: str
    task_kind: str
    input_modalities: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "suite_id": self.suite_id,
            "version": self.version,
            "sample_count": self.sample_count,
            "split": self.split,
            "task_kind": self.task_kind,
            "input_modalities": list(self.input_modalities),
        }


@dataclass(frozen=True)
class EvaluationMetricValue:
    name: str
    value: float
    unit: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
        }


@dataclass(frozen=True)
class EvaluationJob:
    schema_version: str
    job_id: str
    model_id: str
    task_kind: str
    source_repo: str
    suite_id: str
    dataset_id: str
    sample_size: int
    scoring_mode: str
    few_shot: int
    seed: int
    code_exec_policy: str
    parameters: dict[str, str]
    status: str
    output_dir: str
    created_at_unix_ms: int
    updated_at_unix_ms: int

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "model_id": self.model_id,
            "task_kind": self.task_kind,
            "source_repo": self.source_repo,
            "suite_id": self.suite_id,
            "dataset_id": self.dataset_id,
            "sample_size": self.sample_size,
            "scoring_mode": self.scoring_mode,
            "few_shot": self.few_shot,
            "seed": self.seed,
            "code_exec_policy": self.code_exec_policy,
            "parameters": dict(self.parameters),
            "status": self.status,
            "output_dir": self.output_dir,
            "created_at_unix_ms": self.created_at_unix_ms,
            "updated_at_unix_ms": self.updated_at_unix_ms,
        }


@dataclass(frozen=True)
class EvaluationResult:
    schema_version: str
    job_id: str
    suite_id: str
    dataset_id: str
    sample_size: int
    score_name: str
    score_value: float
    correct_count: int
    incorrect_count: int
    duration_seconds: float
    metrics: tuple[EvaluationMetricValue, ...]
    report_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "suite_id": self.suite_id,
            "dataset_id": self.dataset_id,
            "sample_size": self.sample_size,
            "score_name": self.score_name,
            "score_value": self.score_value,
            "correct_count": self.correct_count,
            "incorrect_count": self.incorrect_count,
            "duration_seconds": self.duration_seconds,
            "metrics": [metric.to_dict() for metric in self.metrics],
            "report_path": self.report_path,
        }


@dataclass(frozen=True)
class EvaluationSample:
    schema_version: str
    job_id: str
    suite_id: str
    dataset_id: str
    sample_id: str
    question: str
    expected: str
    predicted: str
    raw_response: str
    correct: bool
    time_s: float
    parse_status: str
    task_kind: str
    input_modalities: tuple[str, ...]
    media_references: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "suite_id": self.suite_id,
            "dataset_id": self.dataset_id,
            "sample_id": self.sample_id,
            "question": self.question,
            "expected": self.expected,
            "predicted": self.predicted,
            "raw_response": self.raw_response,
            "correct": self.correct,
            "time_s": self.time_s,
            "parse_status": self.parse_status,
            "task_kind": self.task_kind,
            "input_modalities": list(self.input_modalities),
            "media_references": list(self.media_references),
        }


def build_dataset_package_manifest(
    *,
    dataset_id: str,
    suite_id: str,
    version: str,
    sample_count: int,
    split: str,
    task_kind: str = "text-generation",
    input_modalities: tuple[str, ...] = (),
) -> EvaluationDatasetPackageManifest:
    return EvaluationDatasetPackageManifest(
        schema_version=_EVALUATION_DATASET_PACKAGE_SCHEMA_VERSION,
        dataset_id=dataset_id,
        suite_id=suite_id,
        version=version,
        sample_count=sample_count,
        split=split,
        task_kind=task_kind,
        input_modalities=tuple(input_modalities),
    )


def build_evaluation_job_record(
    *,
    job_id: str,
    model_id: str,
    task_kind: str,
    source_repo: str,
    suite_id: str,
    dataset_id: str,
    sample_size: int,
    scoring_mode: str,
    parameters: dict[str, str],
    status: str,
    few_shot: int = 0,
    seed: int = 0,
    code_exec_policy: str = "",
    output_dir: str = "",
    created_at_unix_ms: int = 0,
    updated_at_unix_ms: int = 0,
) -> EvaluationJob:
    return EvaluationJob(
        schema_version=_EVALUATION_JOB_SCHEMA_VERSION,
        job_id=job_id,
        model_id=model_id,
        task_kind=task_kind,
        source_repo=source_repo,
        suite_id=suite_id,
        dataset_id=dataset_id,
        sample_size=sample_size,
        scoring_mode=scoring_mode,
        few_shot=few_shot,
        seed=seed,
        code_exec_policy=code_exec_policy,
        parameters=dict(parameters),
        status=status,
        output_dir=output_dir,
        created_at_unix_ms=created_at_unix_ms,
        updated_at_unix_ms=updated_at_unix_ms,
    )


def build_evaluation_result_record(
    *,
    job_id: str,
    suite_id: str,
    dataset_id: str,
    sample_size: int,
    metrics: dict[str, float],
    report_path: str,
    units: dict[str, str] | None = None,
    score_name: str = "",
    score_value: float = 0.0,
    correct_count: int = 0,
    incorrect_count: int = 0,
    duration_seconds: float = 0.0,
) -> EvaluationResult:
    metric_units = units or {}
    ordered_metrics = tuple(
        EvaluationMetricValue(name=name, value=float(value), unit=metric_units.get(name, ""))
        for name, value in sorted(metrics.items())
    )
    return EvaluationResult(
        schema_version=_EVALUATION_RESULT_SCHEMA_VERSION,
        job_id=job_id,
        suite_id=suite_id,
        dataset_id=dataset_id,
        sample_size=sample_size,
        score_name=score_name,
        score_value=float(score_value),
        correct_count=correct_count,
        incorrect_count=incorrect_count,
        duration_seconds=float(duration_seconds),
        metrics=ordered_metrics,
        report_path=report_path,
    )


def build_evaluation_sample_record(
    *,
    job_id: str,
    suite_id: str,
    dataset_id: str,
    sample_id: str,
    question: str,
    expected: str,
    predicted: str,
    raw_response: str,
    correct: bool,
    time_s: float,
    parse_status: str,
    task_kind: str = "text-generation",
    input_modalities: tuple[str, ...] = (),
    media_references: tuple[str, ...] = (),
) -> EvaluationSample:
    return EvaluationSample(
        schema_version=_EVALUATION_SAMPLE_SCHEMA_VERSION,
        job_id=job_id,
        suite_id=suite_id,
        dataset_id=dataset_id,
        sample_id=sample_id,
        question=question,
        expected=expected,
        predicted=predicted,
        raw_response=raw_response,
        correct=correct,
        time_s=float(time_s),
        parse_status=parse_status,
        task_kind=task_kind,
        input_modalities=tuple(input_modalities),
        media_references=tuple(media_references),
    )
