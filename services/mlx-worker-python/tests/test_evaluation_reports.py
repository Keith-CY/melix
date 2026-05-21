from __future__ import annotations

from worker.productization.evaluation_reports import build_evaluation_compare_report_markdown
from worker.productization.evaluation_schemas import (
    build_evaluation_compare_job_record,
    build_evaluation_compare_summary_record,
)


def _compare_job() -> object:
    return build_evaluation_compare_job_record(
        job_id="eval-compare-release-report",
        base_model_id="melix-dev-text",
        target_model_ids=(
            "melix-dev-text-lora-improved",
            "melix-dev-text-lora-regressed",
            "melix-dev-text-lora-inconclusive",
        ),
        task_kind="text-generation",
        source_repo="melix.report.fixture",
        suite_id="mmlu",
        dataset_id="mmlu-dev",
        sample_size=8,
        scoring_mode="multiple_choice_accuracy",
        parameters={"compare_mode": "base_vs_targets"},
        status="completed",
    )


def _compare_summary(
    *,
    target_model_id: str,
    verdict: str,
    delta_accuracy: float,
    regression_count: int,
) -> object:
    return build_evaluation_compare_summary_record(
        job_id="eval-compare-release-report",
        base_model_id="melix-dev-text",
        target_model_id=target_model_id,
        suite_id="mmlu",
        dataset_id="mmlu-dev",
        sample_size=8,
        scoring_mode="multiple_choice_accuracy",
        win_count=6 if verdict == "improvement" else 1,
        loss_count=1 if verdict == "regression" else 0,
        tie_count=1,
        regression_count=regression_count,
        base_accuracy=0.5,
        target_accuracy=0.5 + delta_accuracy,
        delta_accuracy=delta_accuracy,
        effect_threshold=0.1,
        verdict=verdict,
        category_breakdown={},
        statistical_evidence={
            "sample_size": 8,
            "delta_accuracy": delta_accuracy,
            "bootstrap": {
                "method": "paired_bootstrap_percentile",
                "confidence_level": 0.95,
                "lower_bound": delta_accuracy - 0.05,
                "upper_bound": delta_accuracy + 0.05,
                "crosses_zero": verdict == "inconclusive",
                "iterations": 400,
                "seed": 9,
            },
            "analytical": {
                "method": "paired_difference_normal_approximation",
                "confidence_level": 0.95,
                "lower_bound": delta_accuracy - 0.04,
                "upper_bound": delta_accuracy + 0.04,
                "crosses_zero": verdict == "inconclusive",
            },
        },
        release_gate_summary={
            "verdict": verdict,
            "reason": "confidence_intervals_cross_zero"
            if verdict == "inconclusive"
            else "delta_exceeds_threshold_with_supported_intervals",
            "effect_threshold": 0.1,
            "delta_accuracy": delta_accuracy,
            "threshold_passed": verdict != "inconclusive",
            "both_intervals_same_side": verdict != "inconclusive",
        },
        duration_seconds=0.25,
        metrics={"eval.compare.delta_accuracy": delta_accuracy},
        report_path="/tmp/evaluation-compare-report.md",
    )


def test_evaluation_compare_report_groups_release_verdicts() -> None:
    markdown = build_evaluation_compare_report_markdown(
        job=_compare_job(),
        summaries=(
            _compare_summary(
                target_model_id="melix-dev-text-lora-improved",
                verdict="improvement",
                delta_accuracy=0.25,
                regression_count=0,
            ),
            _compare_summary(
                target_model_id="melix-dev-text-lora-regressed",
                verdict="regression",
                delta_accuracy=-0.25,
                regression_count=5,
            ),
            _compare_summary(
                target_model_id="melix-dev-text-lora-inconclusive",
                verdict="inconclusive",
                delta_accuracy=0.02,
                regression_count=0,
            ),
        ),
    )

    assert "## Release Verdict Groups" in markdown
    assert "### Quality Improvements" in markdown
    assert (
        "| melix-dev-text-lora-improved | improvement | +0.2500 | 0.1000 | 0 | "
        in markdown
    )
    assert "### Regressions" in markdown
    assert (
        "| melix-dev-text-lora-regressed | regression | -0.2500 | 0.1000 | 5 | "
        in markdown
    )
    assert "### Inconclusive Results" in markdown
    assert (
        "| melix-dev-text-lora-inconclusive | inconclusive | +0.0200 | 0.1000 | 0 | "
        in markdown
    )
    assert "## melix-dev-text-lora-improved" in markdown
    assert "## melix-dev-text-lora-regressed" in markdown
    assert "## melix-dev-text-lora-inconclusive" in markdown


def test_evaluation_compare_report_marks_empty_verdict_groups() -> None:
    markdown = build_evaluation_compare_report_markdown(
        job=_compare_job(),
        summaries=(
            _compare_summary(
                target_model_id="melix-dev-text-lora-improved",
                verdict="improvement",
                delta_accuracy=0.25,
                regression_count=0,
            ),
        ),
    )

    assert "### Quality Improvements" in markdown
    assert "| melix-dev-text-lora-improved | improvement | +0.2500 | 0.1000 | 0 | " in markdown
    assert "### Regressions\n\n| Target Model | Verdict" in markdown
    assert "| None |  |  |  |  |  |  |" in markdown
    assert "### Inconclusive Results\n\n| Target Model | Verdict" in markdown
