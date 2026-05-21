from __future__ import annotations

from worker.productization.evaluation_schemas import EvaluationCompareJob, EvaluationCompareSummary

_VERDICT_GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("quality_improvements", "Quality Improvements", ("improvement",)),
    ("regressions", "Regressions", ("regression",)),
    ("inconclusive_results", "Inconclusive Results", ("inconclusive",)),
)


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
    lines.extend(_verdict_group_sections(summaries))
    for summary in summaries:
        bootstrap_interval = summary.statistical_evidence.get("bootstrap", {})
        analytical_interval = summary.statistical_evidence.get("analytical", {})
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


def _verdict_group_sections(summaries: tuple[EvaluationCompareSummary, ...]) -> list[str]:
    lines: list[str] = [
        "",
        "## Release Verdict Groups",
    ]
    handled_verdicts = {
        verdict for _group_id, _label, verdicts in _VERDICT_GROUPS for verdict in verdicts
    }
    for _group_id, label, verdicts in _VERDICT_GROUPS:
        grouped = tuple(summary for summary in summaries if summary.verdict in verdicts)
        lines.extend(_verdict_group_section(label=label, summaries=grouped))

    other_summaries = tuple(
        summary for summary in summaries if summary.verdict not in handled_verdicts
    )
    if other_summaries:
        lines.extend(_verdict_group_section(label="Other Verdicts", summaries=other_summaries))
    return lines


def _verdict_group_section(
    *,
    label: str,
    summaries: tuple[EvaluationCompareSummary, ...],
) -> list[str]:
    lines = [
        "",
        f"### {label}",
        "",
        "| Target Model | Verdict | Delta Accuracy | Effect Threshold | Regressions | Bootstrap CI | Analytical CI |",
        "| --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    if not summaries:
        lines.append("| None |  |  |  |  |  |  |")
        return lines

    for summary in summaries:
        bootstrap_interval = summary.statistical_evidence.get("bootstrap", {})
        analytical_interval = summary.statistical_evidence.get("analytical", {})
        lines.append(
            "| "
            + " | ".join(
                [
                    summary.target_model_id,
                    summary.verdict,
                    _signed_ratio(summary.delta_accuracy),
                    _ratio(summary.effect_threshold),
                    str(summary.regression_count),
                    _interval(bootstrap_interval),
                    _interval(analytical_interval),
                ]
            )
            + " |"
        )
    return lines


def _ratio(value: float) -> str:
    return f"{value:.4f}"


def _signed_ratio(value: float) -> str:
    return f"{value:+.4f}"


def _interval(interval: dict[str, object]) -> str:
    return (
        f"[{float(interval.get('lower_bound', 0.0)):.4f}, "
        f"{float(interval.get('upper_bound', 0.0)):.4f}]"
    )
