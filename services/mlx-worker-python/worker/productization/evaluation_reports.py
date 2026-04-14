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
        "| Target Model | Verdict | Wins | Losses | Ties | Regressions | Base Accuracy | Target Accuracy | Delta Accuracy | Bootstrap CI | Analytical CI |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for summary in summaries:
        bootstrap_interval = summary.statistical_evidence.get("bootstrap", {})
        analytical_interval = summary.statistical_evidence.get("analytical", {})
        lines.append(
            "| "
            + " | ".join(
                [
                    summary.target_model_id,
                    summary.verdict,
                    str(summary.win_count),
                    str(summary.loss_count),
                    str(summary.tie_count),
                    str(summary.regression_count),
                    _ratio(summary.base_accuracy),
                    _ratio(summary.target_accuracy),
                    _signed_ratio(summary.delta_accuracy),
                    _interval(bootstrap_interval),
                    _interval(analytical_interval),
                ]
            )
            + " |"
        )
        lines.extend(
            [
                "",
                f"## {summary.target_model_id}",
                "",
                f"- Verdict: `{summary.verdict}`",
                f"- Effect Threshold: `{summary.effect_threshold:.4f}`",
                f"- Bootstrap CI: `{_interval(bootstrap_interval)}`",
                f"- Analytical CI: `{_interval(analytical_interval)}`",
            ]
        )
        release_gate_summary = summary.release_gate_summary
        if release_gate_summary:
            lines.append(
                f"- Release Summary: `{release_gate_summary.get('reason', '')}`"
            )
        category_breakdown = summary.category_breakdown
        if category_breakdown:
            lines.extend(
                [
                    "",
                    "### Category Breakdown",
                    "",
                    "| Category | Sample Size | Base Accuracy | Target Accuracy | Delta Accuracy |",
                    "| --- | ---: | ---: | ---: | ---: |",
                ]
            )
            for category_label, category_metrics in category_breakdown.items():
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            category_label,
                            str(category_metrics.get("sample_size", 0)),
                            _ratio(float(category_metrics.get("base_accuracy", 0.0))),
                            _ratio(float(category_metrics.get("target_accuracy", 0.0))),
                            _signed_ratio(float(category_metrics.get("delta_accuracy", 0.0))),
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


def _interval(interval: dict[str, object]) -> str:
    return (
        f"[{float(interval.get('lower_bound', 0.0)):.4f}, "
        f"{float(interval.get('upper_bound', 0.0)):.4f}]"
    )
