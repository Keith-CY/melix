from __future__ import annotations

from dataclasses import dataclass


_EVALUATION_DATASET_PACKAGE_SCHEMA_VERSION = "melix.evaluation_dataset_package.v1"
_EVALUATION_JOB_SCHEMA_VERSION = "melix.evaluation_job.v1"
_EVALUATION_RESULT_SCHEMA_VERSION = "melix.evaluation_result.v1"


@dataclass(frozen=True)
class EvaluationDatasetPackageManifest:
    schema_version: str
    dataset_id: str
    suite_id: str
    version: str
    sample_count: int
    split: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "suite_id": self.suite_id,
            "version": self.version,
            "sample_count": self.sample_count,
            "split": self.split,
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
    suite_id: str
    dataset_id: str
    sample_size: int
    scoring_mode: str
    parameters: dict[str, str]
    status: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "model_id": self.model_id,
            "suite_id": self.suite_id,
            "dataset_id": self.dataset_id,
            "sample_size": self.sample_size,
            "scoring_mode": self.scoring_mode,
            "parameters": dict(self.parameters),
            "status": self.status,
        }


@dataclass(frozen=True)
class EvaluationResult:
    schema_version: str
    job_id: str
    suite_id: str
    dataset_id: str
    sample_size: int
    metrics: tuple[EvaluationMetricValue, ...]
    report_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "suite_id": self.suite_id,
            "dataset_id": self.dataset_id,
            "sample_size": self.sample_size,
            "metrics": [metric.to_dict() for metric in self.metrics],
            "report_path": self.report_path,
        }


def build_dataset_package_manifest(
    *, dataset_id: str, suite_id: str, version: str, sample_count: int, split: str
) -> EvaluationDatasetPackageManifest:
    return EvaluationDatasetPackageManifest(
        schema_version=_EVALUATION_DATASET_PACKAGE_SCHEMA_VERSION,
        dataset_id=dataset_id,
        suite_id=suite_id,
        version=version,
        sample_count=sample_count,
        split=split,
    )


def build_evaluation_job_record(
    *,
    job_id: str,
    model_id: str,
    suite_id: str,
    dataset_id: str,
    sample_size: int,
    scoring_mode: str,
    parameters: dict[str, str],
    status: str,
) -> EvaluationJob:
    return EvaluationJob(
        schema_version=_EVALUATION_JOB_SCHEMA_VERSION,
        job_id=job_id,
        model_id=model_id,
        suite_id=suite_id,
        dataset_id=dataset_id,
        sample_size=sample_size,
        scoring_mode=scoring_mode,
        parameters=dict(parameters),
        status=status,
    )


def build_evaluation_result_record(
    *,
    job_id: str,
    suite_id: str,
    dataset_id: str,
    sample_size: int,
    metrics: dict[str, float],
    report_path: str,
) -> EvaluationResult:
    ordered_metrics = tuple(
        EvaluationMetricValue(name=name, value=float(value))
        for name, value in sorted(metrics.items())
    )
    return EvaluationResult(
        schema_version=_EVALUATION_RESULT_SCHEMA_VERSION,
        job_id=job_id,
        suite_id=suite_id,
        dataset_id=dataset_id,
        sample_size=sample_size,
        metrics=ordered_metrics,
        report_path=report_path,
    )
