from __future__ import annotations

from dataclasses import dataclass


_EVALUATION_DATASET_PACKAGE_SCHEMA_VERSION = "melix.evaluation_dataset_package.v1"
_EVALUATION_JOB_SCHEMA_VERSION = "melix.evaluation_job.v1"
_EVALUATION_RESULT_SCHEMA_VERSION = "melix.evaluation_result.v1"
_EVALUATION_SAMPLE_SCHEMA_VERSION = "melix.evaluation_sample.v1"
_EVALUATION_COMPARE_JOB_SCHEMA_VERSION = "melix.evaluation_compare_job.v1"
_EVALUATION_COMPARE_SUMMARY_SCHEMA_VERSION = "melix.evaluation_compare_summary.v1"
_EVALUATION_COMPARE_SAMPLE_SCHEMA_VERSION = "melix.evaluation_compare_sample.v1"


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
    code_language: str
    code_entry_point: str
    code_compile_status: str
    code_runtime_status: str
    code_timeout_status: str
    code_test_status: str
    code_tests_passed: int
    code_tests_total: int
    code_failure_detail: str
    category_label: str = ""
    subject_label: str = ""

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
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
            "code_language": self.code_language,
            "code_entry_point": self.code_entry_point,
            "code_compile_status": self.code_compile_status,
            "code_runtime_status": self.code_runtime_status,
            "code_timeout_status": self.code_timeout_status,
            "code_test_status": self.code_test_status,
            "code_tests_passed": self.code_tests_passed,
            "code_tests_total": self.code_tests_total,
            "code_failure_detail": self.code_failure_detail,
        }
        if self.category_label:
            payload["category_label"] = self.category_label
        if self.subject_label:
            payload["subject_label"] = self.subject_label
        return payload


@dataclass(frozen=True)
class EvaluationCompareJob:
    schema_version: str
    job_id: str
    base_model_id: str
    target_model_ids: tuple[str, ...]
    task_kind: str
    source_repo: str
    suite_id: str
    dataset_id: str
    sample_size: int
    scoring_mode: str
    parameters: dict[str, str]
    status: str
    output_dir: str
    created_at_unix_ms: int
    updated_at_unix_ms: int

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "base_model_id": self.base_model_id,
            "target_model_ids": list(self.target_model_ids),
            "task_kind": self.task_kind,
            "source_repo": self.source_repo,
            "suite_id": self.suite_id,
            "dataset_id": self.dataset_id,
            "sample_size": self.sample_size,
            "scoring_mode": self.scoring_mode,
            "parameters": dict(self.parameters),
            "status": self.status,
            "output_dir": self.output_dir,
            "created_at_unix_ms": self.created_at_unix_ms,
            "updated_at_unix_ms": self.updated_at_unix_ms,
        }


@dataclass(frozen=True)
class EvaluationCompareSummary:
    schema_version: str
    job_id: str
    base_model_id: str
    target_model_id: str
    suite_id: str
    dataset_id: str
    sample_size: int
    scoring_mode: str
    win_count: int
    loss_count: int
    tie_count: int
    regression_count: int
    base_accuracy: float
    target_accuracy: float
    delta_accuracy: float
    effect_threshold: float
    verdict: str
    category_breakdown: dict[str, dict[str, object]]
    statistical_evidence: dict[str, object]
    release_gate_summary: dict[str, object]
    duration_seconds: float
    metrics: tuple[EvaluationMetricValue, ...]
    report_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "base_model_id": self.base_model_id,
            "target_model_id": self.target_model_id,
            "suite_id": self.suite_id,
            "dataset_id": self.dataset_id,
            "sample_size": self.sample_size,
            "scoring_mode": self.scoring_mode,
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "tie_count": self.tie_count,
            "regression_count": self.regression_count,
            "base_accuracy": self.base_accuracy,
            "target_accuracy": self.target_accuracy,
            "delta_accuracy": self.delta_accuracy,
            "effect_threshold": self.effect_threshold,
            "verdict": self.verdict,
            "category_breakdown": {
                key: dict(value)
                for key, value in self.category_breakdown.items()
            },
            "statistical_evidence": dict(self.statistical_evidence),
            "release_gate_summary": dict(self.release_gate_summary),
            "duration_seconds": self.duration_seconds,
            "metrics": [metric.to_dict() for metric in self.metrics],
            "report_path": self.report_path,
        }


@dataclass(frozen=True)
class EvaluationCompareSample:
    schema_version: str
    job_id: str
    suite_id: str
    dataset_id: str
    sample_id: str
    target_model_id: str
    question: str
    expected: str
    base_predicted: str
    target_predicted: str
    base_raw_response: str
    target_raw_response: str
    base_correct: bool
    target_correct: bool
    outcome: str
    regression: bool
    base_time_s: float
    target_time_s: float
    base_parse_status: str
    target_parse_status: str
    code_language: str
    code_entry_point: str
    base_code_compile_status: str
    target_code_compile_status: str
    base_code_runtime_status: str
    target_code_runtime_status: str
    base_code_timeout_status: str
    target_code_timeout_status: str
    base_code_test_status: str
    target_code_test_status: str
    base_code_tests_passed: int
    target_code_tests_passed: int
    base_code_tests_total: int
    target_code_tests_total: int
    base_code_failure_detail: str
    target_code_failure_detail: str
    category_label: str = ""
    subject_label: str = ""

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "suite_id": self.suite_id,
            "dataset_id": self.dataset_id,
            "sample_id": self.sample_id,
            "target_model_id": self.target_model_id,
            "question": self.question,
            "expected": self.expected,
            "base_predicted": self.base_predicted,
            "target_predicted": self.target_predicted,
            "base_raw_response": self.base_raw_response,
            "target_raw_response": self.target_raw_response,
            "base_correct": self.base_correct,
            "target_correct": self.target_correct,
            "outcome": self.outcome,
            "regression": self.regression,
            "base_time_s": self.base_time_s,
            "target_time_s": self.target_time_s,
            "base_parse_status": self.base_parse_status,
            "target_parse_status": self.target_parse_status,
            "code_language": self.code_language,
            "code_entry_point": self.code_entry_point,
            "base_code_compile_status": self.base_code_compile_status,
            "target_code_compile_status": self.target_code_compile_status,
            "base_code_runtime_status": self.base_code_runtime_status,
            "target_code_runtime_status": self.target_code_runtime_status,
            "base_code_timeout_status": self.base_code_timeout_status,
            "target_code_timeout_status": self.target_code_timeout_status,
            "base_code_test_status": self.base_code_test_status,
            "target_code_test_status": self.target_code_test_status,
            "base_code_tests_passed": self.base_code_tests_passed,
            "target_code_tests_passed": self.target_code_tests_passed,
            "base_code_tests_total": self.base_code_tests_total,
            "target_code_tests_total": self.target_code_tests_total,
            "base_code_failure_detail": self.base_code_failure_detail,
            "target_code_failure_detail": self.target_code_failure_detail,
        }
        if self.category_label:
            payload["category_label"] = self.category_label
        if self.subject_label:
            payload["subject_label"] = self.subject_label
        return payload


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
    code_language: str = "",
    code_entry_point: str = "",
    code_compile_status: str = "",
    code_runtime_status: str = "",
    code_timeout_status: str = "",
    code_test_status: str = "",
    code_tests_passed: int = 0,
    code_tests_total: int = 0,
    code_failure_detail: str = "",
    category_label: str = "",
    subject_label: str = "",
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
        code_language=code_language,
        code_entry_point=code_entry_point,
        code_compile_status=code_compile_status,
        code_runtime_status=code_runtime_status,
        code_timeout_status=code_timeout_status,
        code_test_status=code_test_status,
        code_tests_passed=code_tests_passed,
        code_tests_total=code_tests_total,
        code_failure_detail=code_failure_detail,
        category_label=category_label,
        subject_label=subject_label,
    )


def build_evaluation_compare_job_record(
    *,
    job_id: str,
    base_model_id: str,
    target_model_ids: tuple[str, ...],
    task_kind: str,
    source_repo: str,
    suite_id: str,
    dataset_id: str,
    sample_size: int,
    scoring_mode: str,
    parameters: dict[str, str],
    status: str,
    output_dir: str = "",
    created_at_unix_ms: int = 0,
    updated_at_unix_ms: int = 0,
) -> EvaluationCompareJob:
    return EvaluationCompareJob(
        schema_version=_EVALUATION_COMPARE_JOB_SCHEMA_VERSION,
        job_id=job_id,
        base_model_id=base_model_id,
        target_model_ids=tuple(target_model_ids),
        task_kind=task_kind,
        source_repo=source_repo,
        suite_id=suite_id,
        dataset_id=dataset_id,
        sample_size=sample_size,
        scoring_mode=scoring_mode,
        parameters=dict(parameters),
        status=status,
        output_dir=output_dir,
        created_at_unix_ms=created_at_unix_ms,
        updated_at_unix_ms=updated_at_unix_ms,
    )


def build_evaluation_compare_summary_record(
    *,
    job_id: str,
    base_model_id: str,
    target_model_id: str,
    suite_id: str,
    dataset_id: str,
    sample_size: int,
    scoring_mode: str,
    win_count: int,
    loss_count: int,
    tie_count: int,
    regression_count: int,
    base_accuracy: float,
    target_accuracy: float,
    delta_accuracy: float,
    effect_threshold: float,
    verdict: str,
    category_breakdown: dict[str, dict[str, object]],
    statistical_evidence: dict[str, object],
    release_gate_summary: dict[str, object],
    duration_seconds: float,
    metrics: dict[str, float],
    report_path: str,
    units: dict[str, str] | None = None,
) -> EvaluationCompareSummary:
    metric_units = units or {}
    ordered_metrics = tuple(
        EvaluationMetricValue(name=name, value=float(value), unit=metric_units.get(name, ""))
        for name, value in sorted(metrics.items())
    )
    return EvaluationCompareSummary(
        schema_version=_EVALUATION_COMPARE_SUMMARY_SCHEMA_VERSION,
        job_id=job_id,
        base_model_id=base_model_id,
        target_model_id=target_model_id,
        suite_id=suite_id,
        dataset_id=dataset_id,
        sample_size=sample_size,
        scoring_mode=scoring_mode,
        win_count=win_count,
        loss_count=loss_count,
        tie_count=tie_count,
        regression_count=regression_count,
        base_accuracy=float(base_accuracy),
        target_accuracy=float(target_accuracy),
        delta_accuracy=float(delta_accuracy),
        effect_threshold=float(effect_threshold),
        verdict=verdict,
        category_breakdown={
            key: dict(value)
            for key, value in sorted(category_breakdown.items())
        },
        statistical_evidence=dict(statistical_evidence),
        release_gate_summary=dict(release_gate_summary),
        duration_seconds=float(duration_seconds),
        metrics=ordered_metrics,
        report_path=report_path,
    )


def build_evaluation_compare_sample_record(
    *,
    job_id: str,
    suite_id: str,
    dataset_id: str,
    sample_id: str,
    target_model_id: str,
    question: str,
    expected: str,
    base_predicted: str,
    target_predicted: str,
    base_raw_response: str,
    target_raw_response: str,
    base_correct: bool,
    target_correct: bool,
    outcome: str,
    regression: bool,
    base_time_s: float,
    target_time_s: float,
    base_parse_status: str,
    target_parse_status: str,
    code_language: str = "",
    code_entry_point: str = "",
    base_code_compile_status: str = "",
    target_code_compile_status: str = "",
    base_code_runtime_status: str = "",
    target_code_runtime_status: str = "",
    base_code_timeout_status: str = "",
    target_code_timeout_status: str = "",
    base_code_test_status: str = "",
    target_code_test_status: str = "",
    base_code_tests_passed: int = 0,
    target_code_tests_passed: int = 0,
    base_code_tests_total: int = 0,
    target_code_tests_total: int = 0,
    base_code_failure_detail: str = "",
    target_code_failure_detail: str = "",
    category_label: str = "",
    subject_label: str = "",
) -> EvaluationCompareSample:
    return EvaluationCompareSample(
        schema_version=_EVALUATION_COMPARE_SAMPLE_SCHEMA_VERSION,
        job_id=job_id,
        suite_id=suite_id,
        dataset_id=dataset_id,
        sample_id=sample_id,
        target_model_id=target_model_id,
        question=question,
        expected=expected,
        base_predicted=base_predicted,
        target_predicted=target_predicted,
        base_raw_response=base_raw_response,
        target_raw_response=target_raw_response,
        base_correct=base_correct,
        target_correct=target_correct,
        outcome=outcome,
        regression=regression,
        base_time_s=float(base_time_s),
        target_time_s=float(target_time_s),
        base_parse_status=base_parse_status,
        target_parse_status=target_parse_status,
        code_language=code_language,
        code_entry_point=code_entry_point,
        base_code_compile_status=base_code_compile_status,
        target_code_compile_status=target_code_compile_status,
        base_code_runtime_status=base_code_runtime_status,
        target_code_runtime_status=target_code_runtime_status,
        base_code_timeout_status=base_code_timeout_status,
        target_code_timeout_status=target_code_timeout_status,
        base_code_test_status=base_code_test_status,
        target_code_test_status=target_code_test_status,
        base_code_tests_passed=base_code_tests_passed,
        target_code_tests_passed=target_code_tests_passed,
        base_code_tests_total=base_code_tests_total,
        target_code_tests_total=target_code_tests_total,
        base_code_failure_detail=base_code_failure_detail,
        target_code_failure_detail=target_code_failure_detail,
        category_label=category_label,
        subject_label=subject_label,
    )
