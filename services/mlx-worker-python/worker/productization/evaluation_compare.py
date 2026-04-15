from __future__ import annotations

from typing import Any

from worker.productization.evaluation_schemas import (
    EvaluationCompareSample,
    EvaluationCompareSummary,
    EvaluationSample,
    build_evaluation_compare_sample_record,
    build_evaluation_compare_summary_record,
)
from worker.productization.statistical_evidence import (
    build_category_breakdown,
    build_paired_statistical_evidence,
    classify_release_verdict,
)

_DEFAULT_COMPARE_EFFECT_THRESHOLD = 0.1
_DEFAULT_COMPARE_CONFIDENCE_LEVEL = 0.95
_DEFAULT_COMPARE_BOOTSTRAP_ITERATIONS = 400
_DEFAULT_COMPARE_BOOTSTRAP_SEED = 9


def parse_compare_target_model_ids(parameters: dict[str, str] | None) -> tuple[str, ...]:
    raw_value = (parameters or {}).get("compare_target_model_ids", "")
    target_model_ids = tuple(
        value.strip()
        for value in raw_value.split(",")
        if value.strip()
    )
    if target_model_ids:
        return target_model_ids
    raise ValueError("compare_target_model_ids must include at least one target model ID")


def resolve_compare_target_models(
    *,
    registry: Any | None,
    target_model_ids: tuple[str, ...],
) -> dict[str, Any]:
    if registry is None or hasattr(registry, "list_loaded_models") is False:
        raise ValueError("Evaluation compare requires a live registry with loaded target models.")
    loaded_models_by_id: dict[str, Any] = {}
    for handle in registry.list_loaded_models():
        loaded_model = registry.get_loaded_model(handle)
        if loaded_model is None:
            continue
        model_id = str(getattr(getattr(loaded_model, "spec", None), "model_id", "")).strip()
        if model_id and model_id not in loaded_models_by_id:
            loaded_models_by_id[model_id] = loaded_model
    unknown_targets = [model_id for model_id in target_model_ids if model_id not in loaded_models_by_id]
    if unknown_targets:
        raise ValueError(f"Unknown comparison target model IDs: {', '.join(unknown_targets)}")
    return {model_id: loaded_models_by_id[model_id] for model_id in target_model_ids}


def build_compare_samples(
    *,
    job_id: str,
    suite_id: str,
    dataset_id: str,
    target_model_id: str,
    threshold: float,
    base_samples: tuple[EvaluationSample, ...],
    target_samples: tuple[EvaluationSample, ...],
) -> tuple[EvaluationCompareSample, ...]:
    records: list[EvaluationCompareSample] = []
    for base_sample, target_sample in zip(base_samples, target_samples, strict=True):
        outcome = compare_outcome(
            base_typed_score=base_sample.typed_score,
            target_typed_score=target_sample.typed_score,
            base_validation_status=base_sample.validation_status,
            target_validation_status=target_sample.validation_status,
        )
        regression_kind = compare_regression_kind(
            threshold=threshold,
            base_sample=base_sample,
            target_sample=target_sample,
        )
        records.append(
            build_evaluation_compare_sample_record(
                job_id=job_id,
                suite_id=suite_id,
                dataset_id=dataset_id,
                sample_id=base_sample.sample_id,
                target_model_id=target_model_id,
                input_text=base_sample.input_text,
                target=base_sample.target,
                base_extracted_result=base_sample.extracted_result,
                target_extracted_result=target_sample.extracted_result,
                base_raw_response=base_sample.raw_response,
                target_raw_response=target_sample.raw_response,
                base_typed_score=base_sample.typed_score,
                target_typed_score=target_sample.typed_score,
                outcome=outcome,
                regression_kind=regression_kind,
                base_time_s=base_sample.time_s,
                target_time_s=target_sample.time_s,
                base_extraction_status=base_sample.extraction_status,
                target_extraction_status=target_sample.extraction_status,
                base_validation_status=base_sample.validation_status,
                target_validation_status=target_sample.validation_status,
                base_failure_reason=base_sample.failure_reason,
                target_failure_reason=target_sample.failure_reason,
                base_parse_status=base_sample.extraction_status,
                target_parse_status=target_sample.extraction_status,
                code_language=target_sample.code_language or base_sample.code_language,
                code_entry_point=target_sample.code_entry_point or base_sample.code_entry_point,
                base_code_compile_status=base_sample.code_compile_status,
                target_code_compile_status=target_sample.code_compile_status,
                base_code_runtime_status=base_sample.code_runtime_status,
                target_code_runtime_status=target_sample.code_runtime_status,
                base_code_timeout_status=base_sample.code_timeout_status,
                target_code_timeout_status=target_sample.code_timeout_status,
                base_code_test_status=base_sample.code_test_status,
                target_code_test_status=target_sample.code_test_status,
                base_code_tests_passed=base_sample.code_tests_passed,
                target_code_tests_passed=target_sample.code_tests_passed,
                base_code_tests_total=base_sample.code_tests_total,
                target_code_tests_total=target_sample.code_tests_total,
                base_code_failure_detail=base_sample.code_failure_detail,
                target_code_failure_detail=target_sample.code_failure_detail,
                category_label=base_sample.category_label or target_sample.category_label,
                subject_label=base_sample.subject_label or target_sample.subject_label,
            )
        )
    return tuple(records)


def build_compare_summary(
    *,
    job_id: str,
    base_model_id: str,
    target_model_id: str,
    suite_id: str,
    dataset_id: str,
    sample_size: int,
    scoring_mode: str,
    threshold: float,
    base_samples: tuple[EvaluationSample, ...],
    compare_samples: tuple[EvaluationCompareSample, ...],
    effect_threshold: float = _DEFAULT_COMPARE_EFFECT_THRESHOLD,
    confidence_level: float = _DEFAULT_COMPARE_CONFIDENCE_LEVEL,
    bootstrap_iterations: int = _DEFAULT_COMPARE_BOOTSTRAP_ITERATIONS,
    bootstrap_seed: int = _DEFAULT_COMPARE_BOOTSTRAP_SEED,
    duration_seconds: float,
    report_path: str,
) -> EvaluationCompareSummary:
    win_count = sum(1 for sample in compare_samples if sample.outcome == "win")
    loss_count = sum(1 for sample in compare_samples if sample.outcome == "loss")
    tie_count = sum(1 for sample in compare_samples if sample.outcome == "tie")
    regression_count = sum(1 for sample in compare_samples if sample.regression_kind != "")
    base_accuracy = round(
        sum(
            1
            for sample in base_samples
            if sample.validation_status == "validated" and sample.typed_score >= threshold
        )
        / max(sample_size, 1),
        4,
    )
    target_accuracy = round(
        sum(
            1
            for sample in compare_samples
            if sample.target_validation_status == "validated" and sample.target_typed_score >= threshold
        )
        / max(sample_size, 1),
        4,
    )
    delta_accuracy = round(target_accuracy - base_accuracy, 4)
    base_typed_score_mean = round(
        sum(sample.typed_score for sample in base_samples) / max(sample_size, 1),
        4,
    )
    target_typed_score_mean = round(
        sum(sample.target_typed_score for sample in compare_samples) / max(sample_size, 1),
        4,
    )
    delta_typed_score_mean = round(target_typed_score_mean - base_typed_score_mean, 4)
    base_extraction_success_rate = round(
        sum(1 for sample in base_samples if sample.extraction_status == "extracted")
        / max(sample_size, 1),
        4,
    )
    target_extraction_success_rate = round(
        sum(1 for sample in compare_samples if sample.target_extraction_status == "extracted")
        / max(sample_size, 1),
        4,
    )
    base_validation_success_rate = round(
        sum(1 for sample in base_samples if sample.validation_status == "validated")
        / max(sample_size, 1),
        4,
    )
    target_validation_success_rate = round(
        sum(1 for sample in compare_samples if sample.target_validation_status == "validated")
        / max(sample_size, 1),
        4,
    )
    extraction_failure_regression_count = sum(
        1 for sample in compare_samples if sample.regression_kind == "extraction_failure"
    )
    validation_failure_regression_count = sum(
        1 for sample in compare_samples if sample.regression_kind == "validation_failure"
    )
    score_regression_count = sum(
        1 for sample in compare_samples if sample.regression_kind == "score_regression"
    )
    category_rows: tuple[dict[str, object], ...] = tuple(
        {
            "category_label": sample.category_label,
            "base_correct": (
                sample.base_validation_status == "validated" and sample.base_typed_score >= threshold
            ),
            "target_correct": (
                sample.target_validation_status == "validated" and sample.target_typed_score >= threshold
            ),
        }
        for sample in compare_samples
    )
    paired_outcomes = tuple(
        int(row["target_correct"]) - int(row["base_correct"])
        for row in category_rows
    )
    statistical_evidence = build_paired_statistical_evidence(
        paired_outcomes=paired_outcomes,
        confidence_level=confidence_level,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
    )
    release_gate_summary = classify_release_verdict(
        delta_accuracy=delta_accuracy,
        effect_threshold=effect_threshold,
        bootstrap_interval=dict(statistical_evidence.get("bootstrap", {})),
        analytical_interval=dict(statistical_evidence.get("analytical", {})),
    )
    category_breakdown = build_category_breakdown(rows=category_rows)
    return build_evaluation_compare_summary_record(
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
        base_accuracy=base_accuracy,
        target_accuracy=target_accuracy,
        delta_accuracy=delta_accuracy,
        effect_threshold=effect_threshold,
        verdict=str(release_gate_summary["verdict"]),
        category_breakdown=category_breakdown,
        statistical_evidence=statistical_evidence,
        release_gate_summary=release_gate_summary,
        duration_seconds=duration_seconds,
        metrics={
            "eval.compare.base_accuracy": base_accuracy,
            "eval.compare.delta_accuracy": delta_accuracy,
            "eval.compare.effect_threshold": float(effect_threshold),
            "eval.compare.base_typed_score_mean": base_typed_score_mean,
            "eval.compare.target_typed_score_mean": target_typed_score_mean,
            "eval.compare.delta_typed_score_mean": delta_typed_score_mean,
            "eval.compare.base_extraction_success_rate": base_extraction_success_rate,
            "eval.compare.target_extraction_success_rate": target_extraction_success_rate,
            "eval.compare.base_validation_success_rate": base_validation_success_rate,
            "eval.compare.target_validation_success_rate": target_validation_success_rate,
            "eval.compare.loss_count": float(loss_count),
            "eval.compare.regression_count": float(regression_count),
            "eval.compare.regression.extraction_failure_count": float(extraction_failure_regression_count),
            "eval.compare.regression.validation_failure_count": float(validation_failure_regression_count),
            "eval.compare.regression.score_count": float(score_regression_count),
            "eval.compare.target_accuracy": target_accuracy,
            "eval.compare.tie_count": float(tie_count),
            "eval.compare.win_count": float(win_count),
        },
        units={
            "eval.compare.base_accuracy": "ratio",
            "eval.compare.delta_accuracy": "ratio",
            "eval.compare.effect_threshold": "ratio",
            "eval.compare.base_typed_score_mean": "ratio",
            "eval.compare.target_typed_score_mean": "ratio",
            "eval.compare.delta_typed_score_mean": "ratio",
            "eval.compare.base_extraction_success_rate": "ratio",
            "eval.compare.target_extraction_success_rate": "ratio",
            "eval.compare.base_validation_success_rate": "ratio",
            "eval.compare.target_validation_success_rate": "ratio",
            "eval.compare.loss_count": "count",
            "eval.compare.regression_count": "count",
            "eval.compare.regression.extraction_failure_count": "count",
            "eval.compare.regression.validation_failure_count": "count",
            "eval.compare.regression.score_count": "count",
            "eval.compare.target_accuracy": "ratio",
            "eval.compare.tie_count": "count",
            "eval.compare.win_count": "count",
        },
        report_path=report_path,
    )
def compare_outcome(
    *,
    base_typed_score: float,
    target_typed_score: float,
    base_validation_status: str,
    target_validation_status: str,
) -> str:
    base_valid = base_validation_status == "validated"
    target_valid = target_validation_status == "validated"
    if target_valid and not base_valid:
        return "win"
    if base_valid and not target_valid:
        return "loss"
    if base_valid and target_valid:
        if target_typed_score > base_typed_score:
            return "win"
        if target_typed_score < base_typed_score:
            return "loss"
    return "tie"


def compare_regression_kind(
    *,
    threshold: float,
    base_sample: EvaluationSample,
    target_sample: EvaluationSample,
) -> str:
    base_valid = base_sample.validation_status == "validated"
    target_valid = target_sample.validation_status == "validated"
    if base_valid and not target_valid:
        if target_sample.extraction_status != "extracted":
            return "extraction_failure"
        return "validation_failure"
    if base_valid and target_valid and target_sample.typed_score < base_sample.typed_score:
        if base_sample.typed_score >= threshold or target_sample.typed_score < threshold:
            return "score_regression"
    return ""
