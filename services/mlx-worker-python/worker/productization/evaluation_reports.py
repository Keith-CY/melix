from __future__ import annotations

from worker.productization.evaluation_schemas import EvaluationCompareJob, EvaluationCompareSummary


def build_evaluation_compare_report_markdown(
    *,
    job: EvaluationCompareJob,
    summaries: tuple[EvaluationCompareSummary, ...],
) -> str:
    lines = [
        "# Melix Evaluation Compare",
        "",
        f"- Job ID: `{job.job_id}`",
        f"- Base Model: `{job.base_model_id}`",
        f"- Suite: `{job.suite_id}`",
        f"- Dataset: `{job.dataset_id}`",
        f"- Sample Size: `{job.sample_size}`",
        "",
        "| Target Model | Wins | Losses | Ties | Regressions | Base Accuracy | Target Accuracy | Delta Accuracy |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for summary in summaries:
        lines.append(
            "| "
            + " | ".join(
                [
                    summary.target_model_id,
                    str(summary.win_count),
                    str(summary.loss_count),
                    str(summary.tie_count),
                    str(summary.regression_count),
                    _ratio(summary.base_accuracy),
                    _ratio(summary.target_accuracy),
                    _signed_ratio(summary.delta_accuracy),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def _ratio(value: float) -> str:
    return f"{value:.4f}"


def _signed_ratio(value: float) -> str:
    return f"{value:+.4f}"
