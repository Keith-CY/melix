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
    base_samples: tuple[EvaluationSample, ...],
    target_samples: tuple[EvaluationSample, ...],
) -> tuple[EvaluationCompareSample, ...]:
    records: list[EvaluationCompareSample] = []
    for base_sample, target_sample in zip(base_samples, target_samples, strict=True):
        records.append(
            build_evaluation_compare_sample_record(
                job_id=job_id,
                suite_id=suite_id,
                dataset_id=dataset_id,
                sample_id=base_sample.sample_id,
                target_model_id=target_model_id,
                question=base_sample.question,
                expected=base_sample.expected,
                base_predicted=base_sample.predicted,
                target_predicted=target_sample.predicted,
                base_raw_response=base_sample.raw_response,
                target_raw_response=target_sample.raw_response,
                base_correct=base_sample.correct,
                target_correct=target_sample.correct,
                outcome=compare_outcome(base_correct=base_sample.correct, target_correct=target_sample.correct),
                regression=base_sample.correct and not target_sample.correct,
                base_time_s=base_sample.time_s,
                target_time_s=target_sample.time_s,
                base_parse_status=base_sample.parse_status,
                target_parse_status=target_sample.parse_status,
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
    regression_count = sum(1 for sample in compare_samples if sample.regression)
    base_accuracy = round(
        sum(1 for sample in base_samples if sample.correct) / max(sample_size, 1),
        4,
    )
    target_accuracy = round(
        sum(1 for sample in compare_samples if sample.target_correct) / max(sample_size, 1),
        4,
    )
    delta_accuracy = round(target_accuracy - base_accuracy, 4)
    paired_outcomes = tuple(
        int(sample.target_correct) - int(sample.base_correct)
        for sample in compare_samples
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
    category_breakdown = build_category_breakdown(
        rows=tuple(
            {
                "category_label": sample.category_label,
                "base_correct": sample.base_correct,
                "target_correct": sample.target_correct,
            }
            for sample in compare_samples
        )
    )
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
            "eval.compare.loss_count": float(loss_count),
            "eval.compare.regression_count": float(regression_count),
            "eval.compare.target_accuracy": target_accuracy,
            "eval.compare.tie_count": float(tie_count),
            "eval.compare.win_count": float(win_count),
        },
        units={
            "eval.compare.base_accuracy": "ratio",
            "eval.compare.delta_accuracy": "ratio",
            "eval.compare.effect_threshold": "ratio",
            "eval.compare.loss_count": "count",
            "eval.compare.regression_count": "count",
            "eval.compare.target_accuracy": "ratio",
            "eval.compare.tie_count": "count",
            "eval.compare.win_count": "count",
        },
        report_path=report_path,
    )


def compare_outcome(*, base_correct: bool, target_correct: bool) -> str:
    if target_correct and not base_correct:
        return "win"
    if base_correct and not target_correct:
        return "loss"
    return "tie"
