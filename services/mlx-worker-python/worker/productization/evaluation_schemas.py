from __future__ import annotations

from dataclasses import dataclass

from worker.trajectory_provenance import append_trajectory_provenance


_EVALUATION_DATASET_PACKAGE_SCHEMA_VERSION = "melix.evaluation_dataset_package.v2"
_EVALUATION_JOB_SCHEMA_VERSION = "melix.evaluation_job.v2"
_EVALUATION_RESULT_SCHEMA_VERSION = "melix.evaluation_result.v2"
_EVALUATION_SAMPLE_SCHEMA_VERSION = "melix.evaluation_sample.v2"
_EVALUATION_COMPARE_JOB_SCHEMA_VERSION = "melix.evaluation_compare_job.v2"
_EVALUATION_COMPARE_SUMMARY_SCHEMA_VERSION = "melix.evaluation_compare_summary.v2"
_EVALUATION_COMPARE_SAMPLE_SCHEMA_VERSION = "melix.evaluation_compare_sample.v2"


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
    profile_type: str
    result_kind: str
    extraction_mode: str
    scoring_mode: str
    threshold: float
    output_schema: dict[str, object]
    ignored_paths: tuple[str, ...]
    source_kind: str = ""
    source_path: str = ""

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
            "profile_type": self.profile_type,
            "result_kind": self.result_kind,
            "extraction_mode": self.extraction_mode,
            "scoring_mode": self.scoring_mode,
            "threshold": self.threshold,
            "output_schema": dict(self.output_schema),
            "ignored_paths": list(self.ignored_paths),
            "source_kind": self.source_kind,
            "source_path": self.source_path,
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
    trajectory_provenance: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
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
        append_trajectory_provenance(payload, self.trajectory_provenance)
        return payload


@dataclass(frozen=True)
class EvaluationResult:
    schema_version: str
    job_id: str
    suite_id: str
    dataset_id: str
    sample_size: int
    primary_score_name: str
    primary_score_value: float
    extraction_success_count: int
    validation_success_count: int
    scored_sample_count: int
    failure_count: int
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
            "primary_score_name": self.primary_score_name,
            "primary_score_value": self.primary_score_value,
            "extraction_success_count": self.extraction_success_count,
            "validation_success_count": self.validation_success_count,
            "scored_sample_count": self.scored_sample_count,
            "failure_count": self.failure_count,
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
    system: str
    input_text: str
    target: str
    raw_response: str
    extracted_result: str
    typed_score: float
    time_s: float
    extraction_status: str
    validation_status: str
    failure_reason: str
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
    sample_render_ms: float = 0.0
    inference_ms: float = 0.0
    extraction_ms: float = 0.0
    validation_ms: float = 0.0
    scoring_ms: float = 0.0
    raw_response_chars: int = 0
    extracted_result_chars: int = 0
    failure_stage: str = ""
    tool_calls: tuple[dict[str, object], ...] = ()
    final_answer: str = ""
    parse_status: str = ""
    agentic_tool_registry: dict[str, object] | None = None
    agentic_tool_calls: tuple[dict[str, object], ...] = ()
    agentic_tool_observations: tuple[dict[str, object], ...] = ()
    agentic_tool_metrics: dict[str, float] | None = None
    trajectory_provenance: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "suite_id": self.suite_id,
            "dataset_id": self.dataset_id,
            "sample_id": self.sample_id,
            "system": self.system,
            "input_text": self.input_text,
            "target": self.target,
            "raw_response": self.raw_response,
            "extracted_result": self.extracted_result,
            "typed_score": self.typed_score,
            "time_s": self.time_s,
            "extraction_status": self.extraction_status,
            "validation_status": self.validation_status,
            "failure_reason": self.failure_reason,
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
            "sample_render_ms": self.sample_render_ms,
            "inference_ms": self.inference_ms,
            "extraction_ms": self.extraction_ms,
            "validation_ms": self.validation_ms,
            "scoring_ms": self.scoring_ms,
            "raw_response_chars": self.raw_response_chars,
            "extracted_result_chars": self.extracted_result_chars,
            "failure_stage": self.failure_stage,
            "final_answer": self.final_answer,
            "parse_status": self.parse_status,
        }
        if self.tool_calls:
            payload["tool_calls"] = [dict(call) for call in self.tool_calls]
        if self.agentic_tool_registry:
            payload["agentic_tool_registry"] = dict(self.agentic_tool_registry)
        if self.agentic_tool_calls:
            payload["agentic_tool_calls"] = [dict(call) for call in self.agentic_tool_calls]
        if self.agentic_tool_observations:
            payload["agentic_tool_observations"] = [
                dict(observation) for observation in self.agentic_tool_observations
            ]
        if self.agentic_tool_metrics:
            payload["agentic_tool_metrics"] = dict(self.agentic_tool_metrics)
        append_trajectory_provenance(payload, self.trajectory_provenance)
        if self.category_label:
            payload["category_label"] = self.category_label
        if self.subject_label:
            payload["subject_label"] = self.subject_label
        return payload


@dataclass(frozen=True)
class EvaluationCompareTargetLineage:
    """Module 2 — per-target provenance for compare jobs.

    Records how each compare target came into being so downstream exports
    preserve which adapter produced which target column. ``materialization_kind``
    is ``"registered"`` for traditional pre-loaded model_id targets (where
    the adapter fields stay empty) or ``"ephemeral_adapter"`` for targets
    materialized on-demand from a ``melix.lora_adapter_package.v1`` manifest
    during the compare run.
    """

    target_model_id: str
    materialization_kind: str
    adapter_manifest_path: str = ""
    adapter_weights_path: str = ""
    adapter_set_hash: str = ""
    derived_from_model_id: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "target_model_id": self.target_model_id,
            "materialization_kind": self.materialization_kind,
            "adapter_manifest_path": self.adapter_manifest_path,
            "adapter_weights_path": self.adapter_weights_path,
            "adapter_set_hash": self.adapter_set_hash,
            "derived_from_model_id": self.derived_from_model_id,
        }


@dataclass(frozen=True)
class EvaluationCompareDatasetLineage:
    """Dataset provenance for paired compare artifacts.

    Compare release evidence needs one stable view of the dataset slice used by
    the base and every target. The normalized source fields mirror the
    evaluation request contract; empty strings are used when a legacy caller did
    not provide the corresponding source detail.
    """

    dataset_id: str
    suite_id: str
    dataset_root: str = ""
    source_kind: str = ""
    source_path: str = ""
    source_dataset_path: str = ""
    source_dataset_name: str = ""
    source_dataset_revision: str = ""
    source_split: str = ""
    sample_size: int = 0
    seed: int = 0
    few_shot: int = 0
    scoring_mode: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "suite_id": self.suite_id,
            "dataset_root": self.dataset_root,
            "source_kind": self.source_kind,
            "source_path": self.source_path,
            "source_dataset_path": self.source_dataset_path,
            "source_dataset_name": self.source_dataset_name,
            "source_dataset_revision": self.source_dataset_revision,
            "source_split": self.source_split,
            "sample_size": self.sample_size,
            "seed": self.seed,
            "few_shot": self.few_shot,
            "scoring_mode": self.scoring_mode,
        }


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
    dataset_lineage: EvaluationCompareDatasetLineage | None = None
    # Module 2 — optional per-target lineage. Empty tuple for legacy jobs
    # that pre-date the adapter-native compare surface; ``to_dict``/``from_dict``
    # handle that as a clean default.
    target_lineage: tuple[EvaluationCompareTargetLineage, ...] = ()
    trajectory_provenance: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
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
            "target_lineage": [entry.to_dict() for entry in self.target_lineage],
        }
        if self.dataset_lineage is not None:
            payload["dataset_lineage"] = self.dataset_lineage.to_dict()
        append_trajectory_provenance(payload, self.trajectory_provenance)
        return payload


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
    input_text: str
    target: str
    base_extracted_result: str
    target_extracted_result: str
    base_raw_response: str
    target_raw_response: str
    base_typed_score: float
    target_typed_score: float
    outcome: str
    regression_kind: str
    base_time_s: float
    target_time_s: float
    base_extraction_status: str
    target_extraction_status: str
    base_validation_status: str
    target_validation_status: str
    base_failure_reason: str
    target_failure_reason: str
    base_parse_status: str = ""
    target_parse_status: str = ""
    code_language: str = ""
    code_entry_point: str = ""
    base_code_compile_status: str = ""
    target_code_compile_status: str = ""
    base_code_runtime_status: str = ""
    target_code_runtime_status: str = ""
    base_code_timeout_status: str = ""
    target_code_timeout_status: str = ""
    base_code_test_status: str = ""
    target_code_test_status: str = ""
    base_code_tests_passed: int = 0
    target_code_tests_passed: int = 0
    base_code_tests_total: int = 0
    target_code_tests_total: int = 0
    base_code_failure_detail: str = ""
    target_code_failure_detail: str = ""
    category_label: str = ""
    subject_label: str = ""
    trajectory_provenance: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "suite_id": self.suite_id,
            "dataset_id": self.dataset_id,
            "sample_id": self.sample_id,
            "target_model_id": self.target_model_id,
            "input_text": self.input_text,
            "target": self.target,
            "base_extracted_result": self.base_extracted_result,
            "target_extracted_result": self.target_extracted_result,
            "base_raw_response": self.base_raw_response,
            "target_raw_response": self.target_raw_response,
            "base_typed_score": self.base_typed_score,
            "target_typed_score": self.target_typed_score,
            "outcome": self.outcome,
            "regression_kind": self.regression_kind,
            "base_time_s": self.base_time_s,
            "target_time_s": self.target_time_s,
            "base_extraction_status": self.base_extraction_status,
            "target_extraction_status": self.target_extraction_status,
            "base_validation_status": self.base_validation_status,
            "target_validation_status": self.target_validation_status,
            "base_failure_reason": self.base_failure_reason,
            "target_failure_reason": self.target_failure_reason,
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
        append_trajectory_provenance(payload, self.trajectory_provenance)
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
    profile_type: str = "final_result",
    result_kind: str = "text",
    extraction_mode: str = "heuristic_final",
    scoring_mode: str = "normalized_exact_match",
    threshold: float = 1.0,
    output_schema: dict[str, object] | None = None,
    ignored_paths: tuple[str, ...] = (),
    source_kind: str = "",
    source_path: str = "",
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
        profile_type=profile_type,
        result_kind=result_kind,
        extraction_mode=extraction_mode,
        scoring_mode=scoring_mode,
        threshold=float(threshold),
        output_schema=dict(output_schema or {}),
        ignored_paths=tuple(ignored_paths),
        source_kind=source_kind,
        source_path=source_path,
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
    trajectory_provenance: dict[str, object] | None = None,
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
        trajectory_provenance=dict(trajectory_provenance or {}),
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
    primary_score_name: str = "",
    primary_score_value: float = 0.0,
    extraction_success_count: int = 0,
    validation_success_count: int = 0,
    scored_sample_count: int = 0,
    failure_count: int = 0,
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
        primary_score_name=primary_score_name,
        primary_score_value=float(primary_score_value),
        extraction_success_count=extraction_success_count,
        validation_success_count=validation_success_count,
        scored_sample_count=scored_sample_count,
        failure_count=failure_count,
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
    system: str,
    input_text: str,
    target: str,
    raw_response: str,
    extracted_result: str,
    typed_score: float,
    time_s: float,
    extraction_status: str,
    validation_status: str,
    failure_reason: str,
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
    sample_render_ms: float = 0.0,
    inference_ms: float = 0.0,
    extraction_ms: float = 0.0,
    validation_ms: float = 0.0,
    scoring_ms: float = 0.0,
    raw_response_chars: int | None = None,
    extracted_result_chars: int | None = None,
    failure_stage: str = "",
    tool_calls: tuple[dict[str, object], ...] = (),
    final_answer: str | None = None,
    parse_status: str | None = None,
    agentic_tool_registry: dict[str, object] | None = None,
    agentic_tool_calls: tuple[dict[str, object], ...] = (),
    agentic_tool_observations: tuple[dict[str, object], ...] = (),
    agentic_tool_metrics: dict[str, float] | None = None,
    trajectory_provenance: dict[str, object] | None = None,
) -> EvaluationSample:
    return EvaluationSample(
        schema_version=_EVALUATION_SAMPLE_SCHEMA_VERSION,
        job_id=job_id,
        suite_id=suite_id,
        dataset_id=dataset_id,
        sample_id=sample_id,
        system=system,
        input_text=input_text,
        target=target,
        raw_response=raw_response,
        extracted_result=extracted_result,
        typed_score=float(typed_score),
        time_s=float(time_s),
        extraction_status=extraction_status,
        validation_status=validation_status,
        failure_reason=failure_reason,
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
        sample_render_ms=float(sample_render_ms),
        inference_ms=float(inference_ms),
        extraction_ms=float(extraction_ms),
        validation_ms=float(validation_ms),
        scoring_ms=float(scoring_ms),
        raw_response_chars=(
            len(raw_response) if raw_response_chars is None else raw_response_chars
        ),
        extracted_result_chars=(
            len(extracted_result)
            if extracted_result_chars is None
            else extracted_result_chars
        ),
        failure_stage=failure_stage,
        tool_calls=tuple(dict(call) for call in tool_calls),
        final_answer=extracted_result if final_answer is None else final_answer,
        parse_status=extraction_status if parse_status is None else parse_status,
        agentic_tool_registry=dict(agentic_tool_registry or {}),
        agentic_tool_calls=tuple(dict(call) for call in agentic_tool_calls),
        agentic_tool_observations=tuple(dict(observation) for observation in agentic_tool_observations),
        agentic_tool_metrics=dict(agentic_tool_metrics or {}),
        trajectory_provenance=dict(trajectory_provenance or {}),
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
    dataset_lineage: EvaluationCompareDatasetLineage | None = None,
    target_lineage: tuple[EvaluationCompareTargetLineage, ...] = (),
    trajectory_provenance: dict[str, object] | None = None,
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
        dataset_lineage=dataset_lineage,
        target_lineage=tuple(target_lineage),
        trajectory_provenance=dict(trajectory_provenance or {}),
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
    input_text: str,
    target: str,
    base_extracted_result: str,
    target_extracted_result: str,
    base_raw_response: str,
    target_raw_response: str,
    base_typed_score: float,
    target_typed_score: float,
    outcome: str,
    regression_kind: str,
    base_time_s: float,
    target_time_s: float,
    base_extraction_status: str,
    target_extraction_status: str,
    base_validation_status: str,
    target_validation_status: str,
    base_failure_reason: str,
    target_failure_reason: str,
    base_parse_status: str = "",
    target_parse_status: str = "",
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
    trajectory_provenance: dict[str, object] | None = None,
) -> EvaluationCompareSample:
    return EvaluationCompareSample(
        schema_version=_EVALUATION_COMPARE_SAMPLE_SCHEMA_VERSION,
        job_id=job_id,
        suite_id=suite_id,
        dataset_id=dataset_id,
        sample_id=sample_id,
        target_model_id=target_model_id,
        input_text=input_text,
        target=target,
        base_extracted_result=base_extracted_result,
        target_extracted_result=target_extracted_result,
        base_raw_response=base_raw_response,
        target_raw_response=target_raw_response,
        base_typed_score=float(base_typed_score),
        target_typed_score=float(target_typed_score),
        outcome=outcome,
        regression_kind=regression_kind,
        base_time_s=float(base_time_s),
        target_time_s=float(target_time_s),
        base_extraction_status=base_extraction_status,
        target_extraction_status=target_extraction_status,
        base_validation_status=base_validation_status,
        target_validation_status=target_validation_status,
        base_failure_reason=base_failure_reason,
        target_failure_reason=target_failure_reason,
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
        trajectory_provenance=dict(trajectory_provenance or {}),
    )
