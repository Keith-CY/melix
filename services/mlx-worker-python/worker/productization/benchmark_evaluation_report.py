from __future__ import annotations

import csv
from datetime import UTC, datetime
import hashlib
import io
from collections.abc import Iterator
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from worker.productization.run_evidence import summarize_run_evidence_probes

_COMMENT_MARKER = "<!-- melix-benchmark-evaluation-report -->"
_REPORT_SCHEMA_VERSION = "melix.benchmark_evaluation_report.v1"
_REPORT_GENERATOR_NAME = "worker.productization.benchmark_evaluation_report"
_REPORT_GENERATOR_VERSION = "2026-05-08.plan4"
_WARNING_THRESHOLD_PCT = 5.0
_RUNTIME_PARAMETER_KEYS = (
    "runtime_live_model",
    "runtime_model_handle",
    "runtime_kind",
    "runtime_name",
    "runtime_model_id",
    "runtime_model_path",
    "runtime_source_kind",
    "runtime_source_repo",
)
_REQUEST_PROBE_KEYS = (
    "dataset_materialize_ms",
    "prompt_render_ms",
    "warmup_ms",
    "prefill_ms",
    "decode_ms",
    "tokens_in",
    "tokens_out",
    "first_token_index",
    "cache_hit",
    "speculative_acceptance_rate",
    "speculative_rollback_rate",
    "speculative_accepted_tokens",
    "speculative_rejected_tokens",
    "speculative_fallback_count",
    "speculative_num_draft_tokens",
    "speculative_draft_model_configured",
    "speculative_draft_propose_ms",
    "speculative_target_verify_ms",
    "dflash_enabled",
    "dflash_block_size",
    "dflash_rollback_count",
    "dflash_target_hidden_layers",
)
_REQUEST_PROBE_KEY_SET = frozenset(_REQUEST_PROBE_KEYS)
_COUNT_PROBE_KEYS = {
    "speculative_accepted_tokens",
    "speculative_rejected_tokens",
    "speculative_fallback_count",
    "dflash_rollback_count",
}
_RATE_PROBE_KEYS = {
    "cache_hit",
    "speculative_draft_model_configured",
    "dflash_enabled",
}
_EVALUATION_SAMPLE_PROBE_KEYS = (
    "sample_render_ms",
    "inference_ms",
    "extraction_ms",
    "validation_ms",
    "scoring_ms",
    "raw_response_chars",
    "extracted_result_chars",
)
_MATRIX_SUMMARY_METRIC_KEYS = (
    "request_latency_mean_ms",
    "request_latency_p95_ms",
    "ttft_mean_ms",
    "ttft_p95_ms",
    "throughput_tokens_per_second",
    "success_rate",
    "failed_count",
)
_EVALUATION_SUMMARY_METRIC_KEYS = ("failure_count", "duration_seconds")
_EVALUATION_REPRODUCIBILITY_KEYS = (
    ("schema_sha256", "schema"),
    ("hints_sha256", "hints"),
)
_LOWER_IS_BETTER_METRIC_FRAGMENTS = (
    "latency",
    "ttft",
    "_ms",
    "duration_seconds",
    "memory",
    "bytes",
    "power_w",
    "watts_per_output_token",
    "failure_count",
    "failed_count",
    "queue_wait",
    "warmup",
    "prefill_ms",
    "decode_ms",
    "rollback_rate",
    "rejected_tokens",
    "fallback_count",
    "draft_propose_ms",
    "target_verify_ms",
    "dflash_rollback_count",
)
_HIGHER_IS_BETTER_METRIC_FRAGMENTS = (
    "tokens_per_second",
    "throughput",
    "success_rate",
    "accuracy",
    "typed_score",
    "pass_rate",
    "win_count",
    "acceptance_rate",
    "accepted_tokens",
    "speedup",
    "cache_hit",
)
_METRIC_DIRECTION_BY_KEY = {
    "cache_hit_rate": "higher_is_better",
    "decode_ms_mean": "lower_is_better",
    "dflash_enabled_rate": "higher_is_better",
    "dflash_rollback_count_sum": "lower_is_better",
    "duration_seconds": "lower_is_better",
    "extracted_result_chars_mean": "neutral",
    "failed_count": "lower_is_better",
    "failure_count": "lower_is_better",
    "inference_ms_mean": "lower_is_better",
    "prefill_ms_mean": "lower_is_better",
    "raw_response_chars_mean": "neutral",
    "request_latency_mean_ms": "lower_is_better",
    "request_latency_p95_ms": "lower_is_better",
    "sample_render_ms_mean": "lower_is_better",
    "scoring_ms_mean": "lower_is_better",
    "speculative_acceptance_rate_mean": "higher_is_better",
    "speculative_fallback_count_sum": "lower_is_better",
    "speculative_rejected_tokens_sum": "lower_is_better",
    "success_rate": "higher_is_better",
    "throughput_tokens_per_second": "higher_is_better",
    "tokens_per_second": "higher_is_better",
    "ttft_mean_ms": "lower_is_better",
    "ttft_ms": "lower_is_better",
    "ttft_p95_ms": "lower_is_better",
    "typed_score_mean": "higher_is_better",
    "validation_ms_mean": "lower_is_better",
}
_RUN_SUMMARY_FIELDS = (
    "side",
    "run_id",
    "trace_id",
    "run_kind",
    "status",
    "started_at",
    "ended_at",
    "duration_ms",
    "command",
    "operator",
    "artifact_root",
    "failure_summary",
    "fallback_summary",
)
_TARGET_FIELDS = (
    "side",
    "run_id",
    "target_model_id",
    "hf_repo_id",
    "task_kind",
    "model_snapshot",
    "adapter_id",
    "adapter_snapshot",
    "runtime_kind",
    "runtime_config",
    "dataset_ref",
    "dataset_revision",
    "suite_id",
    "sample_count",
    "input_digest",
    "prompt_template_digest",
    "generation_config",
)
_TELEMETRY_NUMERIC_FIELDS = (
    "sample_count",
    "average_cpu_utilization_percent",
    "peak_cpu_utilization_percent",
    "average_p_core_utilization_percent",
    "peak_p_core_utilization_percent",
    "average_e_core_utilization_percent",
    "peak_e_core_utilization_percent",
    "average_gpu_utilization_percent",
    "peak_gpu_utilization_percent",
    "average_gpu_frequency_mhz",
    "peak_gpu_frequency_mhz",
    "average_cpu_power_w",
    "peak_cpu_power_w",
    "average_gpu_power_w",
    "peak_gpu_power_w",
    "average_ane_power_w",
    "peak_ane_power_w",
    "average_dram_power_w",
    "peak_dram_power_w",
    "average_system_power_w",
    "peak_system_power_w",
    "watts_per_output_token",
    "memory_used_bytes",
    "memory_total_bytes",
    "peak_process_memory_bytes",
    "average_process_cpu_percent",
)
_TELEMETRY_ZERO_SYNTHESIS_FIELDS = (
    "average_cpu_power_w",
    "peak_cpu_power_w",
    "average_gpu_power_w",
    "peak_gpu_power_w",
    "average_ane_power_w",
    "peak_ane_power_w",
    "average_dram_power_w",
    "peak_dram_power_w",
    "average_system_power_w",
    "peak_system_power_w",
    "watts_per_output_token",
)
_CSV_EXPORT_NAMES = (
    "runs",
    "metrics",
    "probe_phases",
    "telemetry_summary",
    "model_memory",
    "processes",
    "gate_results",
    "comparison_deltas",
)

_NumericAggregate = tuple[float, int]
_ProbeAggregateKey = tuple[str, str]
_BenchmarkLabelCacheKey = tuple[str, str, str, str, str, str]


class ReportValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = tuple(errors)
        super().__init__("; ".join(errors))


def load_report_input(path: str | Path) -> dict[str, object]:
    input_path = Path(path)
    if input_path.is_dir():
        bundle_path = input_path / "benchmark-evaluation-export.json"
        if not bundle_path.is_file():
            bundle_path = input_path / "export-bundle.json"
        input_path = bundle_path
    if not input_path.is_file():
        raise ValueError(f"report input is missing: {input_path}")
    try:
        payload = json.loads(input_path.read_bytes())
    except json.JSONDecodeError as exc:
        raise ValueError(f"report input could not be decoded: {input_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"report input must be a JSON object: {input_path}")
    return payload


def build_benchmark_evaluation_report(
    *,
    baseline: dict[str, object],
    candidate: dict[str, object],
    report_kind: str = "comparison",
) -> dict[str, object]:
    baseline_metrics = _collect_metrics(baseline)
    candidate_metrics = _collect_metrics(candidate)
    reproducibility_warnings = _evaluation_reproducibility_warnings(
        baseline=baseline,
        candidate=candidate,
    )
    metric_names = sorted(set(baseline_metrics) | set(candidate_metrics))
    rows: list[dict[str, object]] = []
    warning_count = 0
    missing_count = 0
    not_comparable_count = 0
    for metric_name in metric_names:
        row = _build_metric_row(
            metric_name=metric_name,
            baseline=baseline_metrics.get(metric_name),
            candidate=candidate_metrics.get(metric_name),
        )
        rows.append(row)
        row_status = row["status"]
        if row_status == "warning":
            warning_count += 1
        elif row_status == "missing":
            missing_count += 1
        elif row_status == "not_comparable":
            not_comparable_count += 1
    warning_count += len(reproducibility_warnings)
    if warning_count:
        status = "warning"
    elif missing_count:
        status = "missing"
    elif not_comparable_count:
        status = "not_comparable"
    else:
        status = "ok"
    baseline_evidence = _run_evidence_rows(baseline)
    candidate_evidence = _run_evidence_rows(candidate)
    source_evidence_ids = _source_evidence_ids(baseline_evidence, candidate_evidence)
    evidence_rows = (*baseline_evidence, *candidate_evidence)
    run_summaries = [
        *_run_summaries("baseline", baseline_evidence),
        *_run_summaries("candidate", candidate_evidence),
    ]
    targets = [
        *_target_summaries("baseline", baseline_evidence),
        *_target_summaries("candidate", candidate_evidence),
    ]
    metric_rows = [_report_metric_row(row) for row in rows]
    probe_summary = {
        "baseline": summarize_run_evidence_probes(baseline_evidence),
        "candidate": summarize_run_evidence_probes(candidate_evidence),
    }
    telemetry_summary = {
        "hardware_banner": "Apple Silicon / macOS telemetry",
        "baseline": _telemetry_summaries("baseline", baseline_evidence),
        "candidate": _telemetry_summaries("candidate", candidate_evidence),
    }
    model_memory_summary = {
        "baseline": _model_memory_summaries("baseline", baseline_evidence),
        "candidate": _model_memory_summaries("candidate", candidate_evidence),
    }
    process_attribution = {
        "baseline": _process_attribution_summaries("baseline", baseline_evidence),
        "candidate": _process_attribution_summaries("candidate", candidate_evidence),
    }
    known_gaps, instrumentation_gaps = _report_gaps(
        source_evidence_ids=source_evidence_ids,
        probe_summary=probe_summary,
        telemetry_summary=telemetry_summary,
    )
    comparison = _comparison_section(
        metric_rows=metric_rows,
        targets=targets,
        baseline_evidence=baseline_evidence,
        candidate_evidence=candidate_evidence,
        reproducibility_warnings=reproducibility_warnings,
    )
    gate_result = _gate_result(
        metric_rows=metric_rows,
        source_evidence_ids=source_evidence_ids,
        probe_summary=probe_summary,
        telemetry_summary=telemetry_summary,
        known_gaps=known_gaps,
    )
    return {
        "schema_version": _REPORT_SCHEMA_VERSION,
        "report_id": _report_id(
            source_evidence_ids=source_evidence_ids,
            rows=rows,
            report_kind=report_kind,
        ),
        "generated_at": _generated_at(evidence_rows),
        "generator_name": _REPORT_GENERATOR_NAME,
        "generator_version": _REPORT_GENERATOR_VERSION,
        "melix_commit": _identity_value(evidence_rows, "melix_commit"),
        "git_branch": _identity_value(evidence_rows, "git_branch"),
        "dirty_worktree": any(bool(row.get("dirty_worktree")) for row in evidence_rows),
        "source_evidence_ids": source_evidence_ids,
        "report_kind": report_kind,
        "summary": {
            "status": status,
            "metric_count": len(rows),
            "warning_count": warning_count,
            "missing_count": missing_count,
            "not_comparable_count": not_comparable_count,
        },
        "runs": run_summaries,
        "targets": targets,
        "metrics": metric_rows,
        "probe_summary": probe_summary,
        "probe_timeline_summary": probe_summary,
        "telemetry_summary": telemetry_summary,
        "model_memory_summary": model_memory_summary,
        "process_attribution": process_attribution,
        "comparison": comparison,
        "reproducibility_warnings": reproducibility_warnings,
        "gate_result": gate_result,
        "artifacts": _default_artifacts(evidence_rows),
        "known_gaps": known_gaps,
        "instrumentation_gaps": instrumentation_gaps,
        "operator_notes": [],
        "non_blocking_warnings": [*instrumentation_gaps, *reproducibility_warnings],
        "rows": rows,
    }


def render_terminal_report(report: dict[str, object]) -> str:
    rows = _report_rows(report)
    headers = ["Metric", "Baseline", "Candidate", "Delta", "Status"]
    rendered_rows = [
        [
            str(row["metric"]),
            _format_value(row.get("baseline")),
            _format_value(row.get("candidate")),
            _format_delta(row),
            str(row["status"]),
        ]
        for row in rows
    ]
    widths = [
        max(len(header), *(len(row[index]) for row in rendered_rows)) if rendered_rows else len(header)
        for index, header in enumerate(headers)
    ]
    lines = [
        "Melix Benchmark/Evaluation Report",
        f"Status: {report.get('summary', {}).get('status', 'ok')}",
        "",
        "  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)),
        "  ".join("-" * width for width in widths),
    ]
    for row in rendered_rows:
        lines.append("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
    return "\n".join(lines) + "\n"


def render_markdown_report(report: dict[str, object]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# Melix Benchmark/Evaluation Report",
        "",
        f"- Status: `{summary.get('status', 'ok')}`",
        f"- Metrics: `{summary.get('metric_count', 0)}`",
        f"- Warnings: `{summary.get('warning_count', 0)}`",
        f"- Missing: `{summary.get('missing_count', 0)}`",
        f"- Not Comparable: `{summary.get('not_comparable_count', 0)}`",
        "",
        "## Report Identity",
        "",
        f"- Report ID: `{report.get('report_id', '')}`",
        f"- Report Kind: `{report.get('report_kind', 'comparison')}`",
        f"- Generated At: `{report.get('generated_at', '')}`",
        f"- Melix Commit: `{report.get('melix_commit', 'unknown')}`",
        f"- Git Branch: `{report.get('git_branch', 'unknown')}`",
        "",
    ]
    lines.extend(_render_run_summary_markdown(report.get("runs")))
    lines.extend(_render_gate_summary_markdown(report.get("gate_result")))
    lines.extend(_render_telemetry_summary_markdown(report.get("telemetry_summary")))
    lines.extend(_render_model_memory_summary_markdown(report.get("model_memory_summary")))
    lines.extend(
        [
            "## Result Metrics",
            "",
        "| Metric | Baseline | Candidate | Delta | Status |",
        "| --- | ---: | ---: | ---: | --- |",
        ]
    )
    for row in _report_rows(report):
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown_cell(row["metric"]),
                    _markdown_cell(_format_value(row.get("baseline"))),
                    _markdown_cell(_format_value(row.get("candidate"))),
                    _markdown_cell(_format_delta(row)),
                    _markdown_cell(row["status"]),
                ]
            )
            + " |"
        )
    probe_summary = report.get("probe_summary")
    if isinstance(probe_summary, dict):
        lines.extend(_render_probe_summary_markdown(probe_summary))
    lines.extend(_render_reproducibility_warnings_markdown(report))
    lines.extend(_render_known_gaps_markdown(report))
    lines.extend(_render_artifacts_markdown(report.get("artifacts")))
    lines.append("")
    return "\n".join(lines)


def build_sticky_comment_body(markdown_report: str) -> str:
    return f"{_COMMENT_MARKER}\n{markdown_report.rstrip()}\n"


def write_report_outputs(
    *,
    report: dict[str, object],
    output_dir: str | Path,
) -> dict[str, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "report.json"
    markdown_path = root / "report.md"
    csv_dir = root / "csv"
    csv_paths = {name: csv_dir / f"{name}.csv" for name in _CSV_EXPORT_NAMES}
    report_payload = _report_with_output_artifacts(
        report=report,
        json_path=json_path,
        markdown_path=markdown_path,
        csv_paths=csv_paths,
    )
    json_path.write_text(json.dumps(report_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown_report(report_payload), encoding="utf-8")
    _write_report_csv_outputs(report_payload, csv_paths)
    outputs = {"json": json_path, "markdown": markdown_path, "csv_dir": csv_dir}
    outputs.update({f"{name}_csv": path for name, path in csv_paths.items()})
    return outputs


def validate_report_payload(report: dict[str, object]) -> list[str]:
    errors: list[str] = []
    for field_name in (
        "schema_version",
        "report_id",
        "generated_at",
        "generator_name",
        "generator_version",
        "melix_commit",
        "git_branch",
        "source_evidence_ids",
        "report_kind",
    ):
        if field_name not in report:
            errors.append(f"missing required report identity field: {field_name}")
        elif field_name != "source_evidence_ids" and not str(report.get(field_name) or "").strip():
            errors.append(f"required report identity field is empty: {field_name}")
    if report.get("schema_version") != _REPORT_SCHEMA_VERSION:
        errors.append(f"schema_version must be {_REPORT_SCHEMA_VERSION}")
    if not isinstance(report.get("source_evidence_ids"), list) or not report.get("source_evidence_ids"):
        errors.append("source_evidence_ids must be a non-empty list")

    runs = report.get("runs")
    if not isinstance(runs, list) or not runs:
        errors.append("runs must be a non-empty list")
    else:
        for index, run in enumerate(runs):
            if not isinstance(run, dict):
                errors.append(f"runs[{index}] must be an object")
                continue
            for field_name in _RUN_SUMMARY_FIELDS:
                if field_name not in run:
                    errors.append(f"runs[{index}] missing required field: {field_name}")
            for field_name in ("run_id", "trace_id", "run_kind", "status", "artifact_root"):
                if field_name in run and not str(run.get(field_name) or "").strip():
                    errors.append(f"runs[{index}] required field is empty: {field_name}")

    targets = report.get("targets")
    if not isinstance(targets, list) or not targets:
        errors.append("targets must be a non-empty list")
    else:
        for index, target in enumerate(targets):
            if not isinstance(target, dict):
                errors.append(f"targets[{index}] must be an object")
                continue
            for field_name in _TARGET_FIELDS:
                if field_name not in target:
                    errors.append(f"targets[{index}] missing required field: {field_name}")
            for field_name in ("run_id", "target_model_id", "task_kind", "suite_id"):
                if field_name in target and not str(target.get(field_name) or "").strip():
                    errors.append(f"targets[{index}] required field is empty: {field_name}")

    metrics = report.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        errors.append("metrics must be a non-empty list")
    else:
        for index, row in enumerate(metrics):
            if not isinstance(row, dict):
                errors.append(f"metrics[{index}] must be an object")
                continue
            if not str(row.get("metric") or "").strip():
                errors.append(f"metrics[{index}] missing metric name")
            if not isinstance(row.get("gate_policy"), dict):
                errors.append(f"metrics[{index}] missing gate_policy")
            if str(row.get("result") or "") not in {"pass", "fail", "informational"}:
                errors.append(f"metrics[{index}] result must be pass, fail, or informational")

    probe_summary = report.get("probe_summary")
    if not isinstance(probe_summary, dict):
        errors.append("probe_summary must be an object")
    else:
        for side in ("baseline", "candidate"):
            side_summary = probe_summary.get(side)
            if not isinstance(side_summary, dict):
                errors.append(f"probe_summary.{side} must be an object")
            elif int(side_summary.get("probe_count") or 0) <= 0:
                errors.append(f"probe_summary.{side}.probe_count must be positive")

    telemetry_summary = report.get("telemetry_summary")
    if not isinstance(telemetry_summary, dict):
        errors.append("telemetry_summary must be an object")
    else:
        for side in ("baseline", "candidate"):
            side_rows = telemetry_summary.get(side)
            if not isinstance(side_rows, list) or not side_rows:
                errors.append(f"telemetry_summary.{side} must be a non-empty list")
                continue
            for index, row in enumerate(side_rows):
                if not isinstance(row, dict):
                    errors.append(f"telemetry_summary.{side}[{index}] must be an object")
                    continue
                if not str(row.get("collector_status") or "").strip():
                    errors.append(f"telemetry_summary.{side}[{index}] missing collector_status")
                if not isinstance(row.get("telemetry_failures"), list):
                    errors.append(f"telemetry_summary.{side}[{index}] missing telemetry_failures")
                errors.extend(_zero_synthesized_telemetry_errors(row, prefix=f"telemetry_summary.{side}[{index}]"))

    gate_result = report.get("gate_result")
    if not isinstance(gate_result, dict):
        errors.append("gate_result must be an object")
    else:
        if str(gate_result.get("overall_result") or "") not in {"pass", "fail", "informational"}:
            errors.append("gate_result.overall_result must be pass, fail, or informational")
        if not isinstance(gate_result.get("gate_results"), list):
            errors.append("gate_result.gate_results must be a list")
        for field_name in (
            "required_evidence_present",
            "required_probe_phases_present",
            "required_telemetry_present",
        ):
            if not isinstance(gate_result.get(field_name), bool):
                errors.append(f"gate_result.{field_name} must be boolean")

    return errors


def assert_valid_report_payload(report: dict[str, object]) -> None:
    errors = validate_report_payload(report)
    if errors:
        raise ReportValidationError(errors)


def _source_evidence_ids(
    baseline_evidence: list[dict[str, object]],
    candidate_evidence: list[dict[str, object]],
) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for evidence in (*baseline_evidence, *candidate_evidence):
        run_id = str(evidence.get("run_id") or "").strip()
        if run_id and run_id not in seen:
            ids.append(run_id)
            seen.add(run_id)
    return ids


def _run_summaries(side: str, evidence_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    for evidence in evidence_rows:
        probes = list(_dict_rows(evidence.get("probe_timeline", [])))
        trace_id = ""
        if probes:
            trace_id = str(probes[0].get("trace_id") or "")
        summaries.append(
            {
                "side": side,
                "run_id": str(evidence.get("run_id") or ""),
                "trace_id": trace_id,
                "run_kind": str(evidence.get("run_kind") or ""),
                "status": str(evidence.get("status") or ""),
                "started_at": evidence.get("started_at"),
                "ended_at": evidence.get("ended_at"),
                "duration_ms": evidence.get("duration_ms"),
                "command": str(evidence.get("command") or ""),
                "operator": str(evidence.get("operator") or ""),
                "artifact_root": str(evidence.get("artifact_root") or ""),
                "failure_summary": dict(evidence.get("failure_summary") or {})
                if isinstance(evidence.get("failure_summary"), dict)
                else {},
                "fallback_summary": dict(evidence.get("fallback_summary") or {})
                if isinstance(evidence.get("fallback_summary"), dict)
                else {},
            }
        )
    return summaries


def _target_summaries(side: str, evidence_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    for evidence in evidence_rows:
        summary = {"side": side}
        for field_name in _TARGET_FIELDS:
            if field_name == "side":
                continue
            value = evidence.get(field_name)
            if isinstance(value, dict):
                summary[field_name] = dict(value)
            else:
                summary[field_name] = value if value is not None else ""
        summaries.append(summary)
    return summaries


def _report_metric_row(row: dict[str, object]) -> dict[str, object]:
    result = _row_result(row)
    return {
        "metric": row.get("metric"),
        "baseline": row.get("baseline"),
        "current": row.get("candidate"),
        "candidate": row.get("candidate"),
        "delta": row.get("delta"),
        "delta_percent": row.get("delta_pct"),
        "delta_pct": row.get("delta_pct"),
        "direction": row.get("direction"),
        "status": row.get("status"),
        "gate_policy": _row_gate_policy(row),
        "result": result,
    }


def _row_result(row: dict[str, object]) -> str:
    status = str(row.get("status") or "")
    if status == "warning":
        return "fail"
    if status in {"missing", "not_comparable"}:
        return "informational"
    return "pass"


def _row_gate_policy(row: dict[str, object]) -> dict[str, object]:
    direction = str(row.get("direction") or "neutral")
    return {
        "direction": direction,
        "warning_threshold_pct": _WARNING_THRESHOLD_PCT,
        "required": direction in {"lower_is_better", "higher_is_better"},
    }


def _telemetry_summaries(side: str, evidence_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    for evidence in evidence_rows:
        telemetry = evidence.get("telemetry_summary")
        if not isinstance(telemetry, dict):
            continue
        failures = telemetry.get("telemetry_failures")
        thermal_events = telemetry.get("thermal_events")
        summary: dict[str, object] = {
            "side": side,
            "run_id": str(evidence.get("run_id") or ""),
            "run_kind": str(evidence.get("run_kind") or ""),
            "collector_status": str(telemetry.get("collector_status") or ""),
            "time_series_path": str(telemetry.get("time_series_path") or ""),
            "telemetry_failures": list(failures) if isinstance(failures, list) else [],
            "thermal_events": list(thermal_events) if isinstance(thermal_events, list) else [],
        }
        for field_name in _TELEMETRY_NUMERIC_FIELDS:
            if field_name in telemetry:
                summary[field_name] = telemetry[field_name]
        process_attribution = telemetry.get("process_attribution")
        if isinstance(process_attribution, dict):
            summary["process_attribution"] = dict(process_attribution)
        summaries.append(summary)
    return summaries


def _model_memory_summaries(side: str, evidence_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    for evidence in evidence_rows:
        memory = evidence.get("model_memory_summary")
        if not isinstance(memory, dict):
            continue
        summary = {
            "side": side,
            "run_id": str(evidence.get("run_id") or ""),
            "run_kind": str(evidence.get("run_kind") or ""),
            "runtime_model_handle": str(memory.get("runtime_model_handle") or ""),
            "runtime_model_id": str(memory.get("runtime_model_id") or ""),
            "runtime_kind": str(memory.get("runtime_kind") or ""),
            "runtime_name": str(memory.get("runtime_name") or ""),
            "loaded_model_estimated_resident_bytes": _int_or_none(
                memory.get("loaded_model_estimated_resident_bytes")
            ) or 0,
            "runtime_stats_model_resident_bytes": _int_or_none(
                memory.get("runtime_stats_model_resident_bytes")
            ) or 0,
            "runtime_stats_resident_bytes": _int_or_none(memory.get("runtime_stats_resident_bytes")) or 0,
            "runtime_stats_cache_resident_bytes": _int_or_none(
                memory.get("runtime_stats_cache_resident_bytes")
            ) or 0,
            "runtime_stats_kv_cache_bytes": _int_or_none(memory.get("runtime_stats_kv_cache_bytes")) or 0,
            "runtime_stats_memory_headroom_bytes": _int_or_none(
                memory.get("runtime_stats_memory_headroom_bytes")
            ) or 0,
            "load_triggered_by_run": bool(memory.get("load_triggered_by_run")),
            "load_rss_delta_bytes": _int_or_none(memory.get("load_rss_delta_bytes")) or 0,
            "load_rss_before_bytes": _int_or_none(memory.get("load_rss_before_bytes")) or 0,
            "load_rss_after_bytes": _int_or_none(memory.get("load_rss_after_bytes")) or 0,
            "measurement_scope": str(memory.get("measurement_scope") or "worker_registry"),
        }
        summaries.append(summary)
    return summaries


def _process_attribution_summaries(
    side: str,
    evidence_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    for evidence in evidence_rows:
        telemetry = evidence.get("telemetry_summary")
        if not isinstance(telemetry, dict):
            continue
        process_attribution = telemetry.get("process_attribution")
        if not isinstance(process_attribution, dict):
            continue
        summaries.append(
            {
                "side": side,
                "run_id": str(evidence.get("run_id") or ""),
                "run_kind": str(evidence.get("run_kind") or ""),
                "primary_runtime_process": dict(process_attribution.get("primary_runtime_process") or {})
                if isinstance(process_attribution.get("primary_runtime_process"), dict)
                else {},
                "control_plane_process": dict(process_attribution.get("control_plane_process") or {})
                if isinstance(process_attribution.get("control_plane_process"), dict)
                else {},
                "worker_processes": list(process_attribution.get("worker_processes") or [])
                if isinstance(process_attribution.get("worker_processes"), list)
                else [],
                "external_provider_processes": list(process_attribution.get("external_provider_processes") or [])
                if isinstance(process_attribution.get("external_provider_processes"), list)
                else [],
                "process_tree_summary": dict(process_attribution.get("process_tree_summary") or {})
                if isinstance(process_attribution.get("process_tree_summary"), dict)
                else {},
            }
        )
    return summaries


def _report_gaps(
    *,
    source_evidence_ids: list[str],
    probe_summary: dict[str, object],
    telemetry_summary: dict[str, object],
) -> tuple[list[str], list[str]]:
    known_gaps: list[str] = []
    instrumentation_gaps: list[str] = []
    if not source_evidence_ids:
        known_gaps.append("run_evidence_missing")
    for side in ("baseline", "candidate"):
        side_probe_summary = probe_summary.get(side)
        if not isinstance(side_probe_summary, dict) or int(side_probe_summary.get("probe_count") or 0) <= 0:
            known_gaps.append(f"{side}_probe_timeline_missing")
        side_telemetry = telemetry_summary.get(side)
        if not isinstance(side_telemetry, list) or not side_telemetry:
            known_gaps.append(f"{side}_telemetry_summary_missing")
            continue
        for row in side_telemetry:
            if not isinstance(row, dict):
                continue
            failures = row.get("telemetry_failures")
            if isinstance(failures, list):
                instrumentation_gaps.extend(
                    f"{side}:{row.get('run_id', '')}:{failure}"
                    for failure in failures
                    if str(failure).strip()
                )
    return known_gaps, instrumentation_gaps


def _evaluation_reproducibility_warnings(
    *,
    baseline: dict[str, object],
    candidate: dict[str, object],
) -> list[str]:
    baseline_values = _evaluation_reproducibility_values(baseline)
    candidate_values = _evaluation_reproducibility_values(candidate)
    warnings: list[str] = []
    for key, label in _EVALUATION_REPRODUCIBILITY_KEYS:
        baseline_hashes = baseline_values.get(key, frozenset())
        candidate_hashes = candidate_values.get(key, frozenset())
        if not baseline_hashes and not candidate_hashes:
            continue
        if baseline_hashes == candidate_hashes:
            continue
        warnings.append(
            f"evaluation_{label}_sha256_mismatch:"
            f"baseline={_format_reproducibility_hashes(baseline_hashes)};"
            f"candidate={_format_reproducibility_hashes(candidate_hashes)}"
        )
    return warnings


def _evaluation_reproducibility_values(
    bundle: dict[str, object],
) -> dict[str, frozenset[str]]:
    values: dict[str, set[str]] = {
        key: set()
        for key, _label in _EVALUATION_REPRODUCIBILITY_KEYS
    }
    for job in (
        *_dict_rows(bundle.get("evaluation_jobs", [])),
        *_dict_rows(bundle.get("evaluation_compare_jobs", [])),
    ):
        _collect_evaluation_reproducibility_parameters(values, job.get("parameters"))
    for evidence in _dict_rows(bundle.get("run_evidence", [])):
        domain_results = evidence.get("domain_results")
        if not isinstance(domain_results, dict):
            continue
        evaluation_domain = domain_results.get("evaluation")
        if not isinstance(evaluation_domain, dict):
            continue
        job = evaluation_domain.get("job")
        if isinstance(job, dict):
            _collect_evaluation_reproducibility_parameters(values, job.get("parameters"))
    return {key: frozenset(item_values) for key, item_values in values.items()}


def _collect_evaluation_reproducibility_parameters(
    values: dict[str, set[str]],
    parameters: object,
) -> None:
    if not isinstance(parameters, dict):
        return
    for key, _label in _EVALUATION_REPRODUCIBILITY_KEYS:
        value = str(parameters.get(key) or "").strip()
        if value:
            values[key].add(value)


def _format_reproducibility_hashes(values: frozenset[str]) -> str:
    if not values:
        return "missing"
    return ",".join(sorted(values))


def _comparison_section(
    *,
    metric_rows: list[dict[str, object]],
    targets: list[dict[str, object]],
    baseline_evidence: list[dict[str, object]],
    candidate_evidence: list[dict[str, object]],
    reproducibility_warnings: list[str],
) -> dict[str, object]:
    metric_deltas = [_comparison_delta(row) for row in metric_rows]
    probe_deltas = [row for row in metric_deltas if str(row.get("metric") or "").startswith("probe.")]
    telemetry_deltas = [
        row for row in metric_deltas if str(row.get("metric") or "").startswith("telemetry.")
    ]
    return {
        "baseline_report_id": _side_report_id("baseline", baseline_evidence),
        "current_report_id": _side_report_id("candidate", candidate_evidence),
        "comparison_dimensions": _comparison_dimensions(targets),
        "metric_deltas": metric_deltas,
        "probe_deltas": probe_deltas,
        "telemetry_deltas": telemetry_deltas,
        "regressions": [row for row in metric_deltas if row.get("result") == "fail"],
        "improvements": [row for row in metric_deltas if _is_improvement(row)],
        "unchanged": [row for row in metric_deltas if _float_or_none(row.get("delta")) == 0.0],
        "reproducibility_warnings": list(reproducibility_warnings),
        "comparison_validity": "valid" if baseline_evidence and candidate_evidence and not reproducibility_warnings else "partial",
    }


def _comparison_delta(row: dict[str, object]) -> dict[str, object]:
    return {
        "metric": row.get("metric"),
        "baseline": row.get("baseline"),
        "current": row.get("current"),
        "delta": row.get("delta"),
        "delta_percent": row.get("delta_percent"),
        "direction": row.get("direction"),
        "gate_policy": row.get("gate_policy"),
        "result": row.get("result"),
    }


def _comparison_dimensions(targets: list[dict[str, object]]) -> list[dict[str, object]]:
    baseline = next((target for target in targets if target.get("side") == "baseline"), None)
    candidate = next((target for target in targets if target.get("side") == "candidate"), None)
    if not isinstance(baseline, dict) or not isinstance(candidate, dict):
        return []
    dimensions: list[dict[str, object]] = []
    for field_name in _TARGET_FIELDS:
        if field_name in {"side", "run_id"}:
            continue
        baseline_value = baseline.get(field_name)
        candidate_value = candidate.get(field_name)
        if baseline_value != candidate_value:
            dimensions.append(
                {
                    "dimension": field_name,
                    "baseline": baseline_value,
                    "current": candidate_value,
                }
            )
    return dimensions


def _gate_result(
    *,
    metric_rows: list[dict[str, object]],
    source_evidence_ids: list[str],
    probe_summary: dict[str, object],
    telemetry_summary: dict[str, object],
    known_gaps: list[str],
) -> dict[str, object]:
    gate_rows = [_gate_row(row) for row in metric_rows]
    informational_rows = [row for row in gate_rows if row.get("result") == "informational"]
    blocking_failures = [row for row in gate_rows if row.get("result") == "fail"]
    required_evidence_present = bool(source_evidence_ids)
    required_probe_phases_present = all(
        isinstance(probe_summary.get(side), dict)
        and int(probe_summary[side].get("probe_count") or 0) > 0
        for side in ("baseline", "candidate")
    )
    required_telemetry_present = all(
        isinstance(telemetry_summary.get(side), list) and bool(telemetry_summary.get(side))
        for side in ("baseline", "candidate")
    )
    if blocking_failures:
        overall_result = "fail"
    elif not (
        required_evidence_present and required_probe_phases_present and required_telemetry_present
    ) or informational_rows:
        overall_result = "informational"
    else:
        overall_result = "pass"
    return {
        "overall_result": overall_result,
        "gate_results": gate_rows,
        "informational_results": informational_rows,
        "known_gaps": list(known_gaps),
        "blocking_failures": blocking_failures,
        "required_evidence_present": required_evidence_present,
        "required_probe_phases_present": required_probe_phases_present,
        "required_telemetry_present": required_telemetry_present,
    }


def _gate_row(row: dict[str, object]) -> dict[str, object]:
    return {
        "metric": row.get("metric"),
        "result": row.get("result"),
        "status": row.get("status"),
        "direction": row.get("direction"),
        "gate_policy": row.get("gate_policy"),
        "baseline": row.get("baseline"),
        "current": row.get("current"),
        "delta": row.get("delta"),
        "delta_percent": row.get("delta_percent"),
    }


def _report_id(
    *,
    source_evidence_ids: list[str],
    rows: list[dict[str, object]],
    report_kind: str,
) -> str:
    payload = {
        "source_evidence_ids": source_evidence_ids,
        "rows": rows,
        "report_kind": report_kind,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return f"report-{digest[:16]}"


def _side_report_id(side: str, evidence_rows: list[dict[str, object]]) -> str:
    run_ids = [str(row.get("run_id") or "") for row in evidence_rows]
    digest = hashlib.sha256(json.dumps(run_ids, sort_keys=True).encode("utf-8")).hexdigest()
    return f"{side}-{digest[:16]}"


def _generated_at(evidence_rows: tuple[dict[str, object], ...]) -> str:
    ended_at_values = [
        value
        for value in (_int_or_none(row.get("ended_at")) for row in evidence_rows)
        if value is not None and value > 0
    ]
    if not ended_at_values:
        return "1970-01-01T00:00:00Z"
    value = max(ended_at_values)
    seconds = value / 1000.0 if value > 10_000_000_000 else float(value)
    return datetime.fromtimestamp(seconds, UTC).isoformat().replace("+00:00", "Z")


def _identity_value(evidence_rows: tuple[dict[str, object], ...], field_name: str) -> str:
    values = sorted({str(row.get(field_name) or "").strip() for row in evidence_rows})
    values = [value for value in values if value]
    if not values:
        return "unknown"
    if len(values) == 1:
        return values[0]
    return ",".join(values)


def _default_artifacts(evidence_rows: tuple[dict[str, object], ...]) -> dict[str, object]:
    raw_output_paths: list[str] = []
    telemetry_paths: list[str] = []
    probe_paths: list[str] = []
    for evidence in evidence_rows:
        artifact_root = str(evidence.get("artifact_root") or "")
        if artifact_root:
            raw_output_paths.append(artifact_root)
        telemetry = evidence.get("telemetry_summary")
        if isinstance(telemetry, dict):
            time_series_path = str(telemetry.get("time_series_path") or "")
            if time_series_path:
                telemetry_paths.append(time_series_path)
        for artifact in _dict_rows(evidence.get("artifacts", [])):
            artifact_path = str(artifact.get("path") or "")
            artifact_kind = str(artifact.get("kind") or "")
            if artifact_path:
                raw_output_paths.append(artifact_path)
            if artifact_kind == "probe_timeline" and artifact_path:
                probe_paths.append(artifact_path)
    return {
        "evidence_json_path": "",
        "report_json_path": "",
        "markdown_report_path": "",
        "csv_export_paths": {},
        "probe_timeline_path": probe_paths[0] if probe_paths else "",
        "telemetry_jsonl_path": telemetry_paths[0] if telemetry_paths else "",
        "raw_output_paths": raw_output_paths,
        "logs_path": "",
        "screenshots_path": "",
        "coverage_path": "",
    }


def _report_with_output_artifacts(
    *,
    report: dict[str, object],
    json_path: Path,
    markdown_path: Path,
    csv_paths: dict[str, Path],
) -> dict[str, object]:
    payload = dict(report)
    artifacts = dict(payload.get("artifacts") or {}) if isinstance(payload.get("artifacts"), dict) else {}
    artifacts["report_json_path"] = str(json_path)
    artifacts["markdown_report_path"] = str(markdown_path)
    artifacts["csv_export_paths"] = {name: str(path) for name, path in csv_paths.items()}
    payload["artifacts"] = artifacts
    return payload


def _zero_synthesized_telemetry_errors(row: dict[str, object], *, prefix: str) -> list[str]:
    failures = row.get("telemetry_failures")
    has_failure = (
        isinstance(failures, list)
        and bool(failures)
        or str(row.get("collector_status") or "") in {"failed", "unsupported"}
    )
    if not has_failure:
        return []
    errors: list[str] = []
    for field_name in _TELEMETRY_ZERO_SYNTHESIS_FIELDS:
        if field_name in row and _float_or_none(row.get(field_name)) == 0.0:
            errors.append(f"{prefix}.{field_name} must not synthesize zero telemetry")
    return errors


def _write_report_csv_outputs(report: dict[str, object], csv_paths: dict[str, Path]) -> None:
    for path in csv_paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(
        csv_paths["runs"],
        _dict_list(report.get("runs")),
        _RUN_SUMMARY_FIELDS,
    )
    _write_csv(
        csv_paths["metrics"],
        _dict_list(report.get("metrics")),
        (
            "metric",
            "baseline",
            "current",
            "candidate",
            "delta",
            "delta_percent",
            "direction",
            "status",
            "result",
            "gate_policy",
        ),
    )
    _write_csv(
        csv_paths["probe_phases"],
        _probe_phase_csv_rows(report),
        (
            "side",
            "scope",
            "run_id",
            "run_kind",
            "bucket",
            "component",
            "phase",
            "duration_ms",
            "status",
            "error_stage",
            "error_code",
        ),
    )
    _write_csv(
        csv_paths["telemetry_summary"],
        _telemetry_csv_rows(report),
        (
            "side",
            "run_id",
            "run_kind",
            "collector_status",
            "sample_count",
            "average_system_power_w",
            "peak_system_power_w",
            "average_cpu_power_w",
            "average_gpu_power_w",
            "average_ane_power_w",
            "average_dram_power_w",
            "watts_per_output_token",
            "peak_process_memory_bytes",
            "average_process_cpu_percent",
            "thermal_events",
            "telemetry_failures",
            "time_series_path",
        ),
    )
    _write_csv(
        csv_paths["model_memory"],
        _model_memory_csv_rows(report),
        (
            "side",
            "run_id",
            "run_kind",
            "runtime_model_handle",
            "runtime_model_id",
            "runtime_kind",
            "runtime_name",
            "loaded_model_estimated_resident_bytes",
            "runtime_stats_model_resident_bytes",
            "runtime_stats_resident_bytes",
            "runtime_stats_cache_resident_bytes",
            "runtime_stats_kv_cache_bytes",
            "runtime_stats_memory_headroom_bytes",
            "load_triggered_by_run",
            "load_rss_delta_bytes",
            "load_rss_before_bytes",
            "load_rss_after_bytes",
            "measurement_scope",
        ),
    )
    _write_csv(
        csv_paths["processes"],
        _process_csv_rows(report),
        (
            "side",
            "run_id",
            "run_kind",
            "group",
            "pid",
            "name",
            "role",
            "port",
            "bundle_prefix",
            "peak_memory_bytes",
            "avg_cpu_percent",
            "sample_count",
            "process_tree_summary",
        ),
    )
    _write_csv(
        csv_paths["gate_results"],
        _dict_list((report.get("gate_result") or {}).get("gate_results") if isinstance(report.get("gate_result"), dict) else []),
        (
            "metric",
            "result",
            "status",
            "direction",
            "baseline",
            "current",
            "delta",
            "delta_percent",
            "gate_policy",
        ),
    )
    _write_csv(
        csv_paths["comparison_deltas"],
        _comparison_delta_csv_rows(report),
        (
            "kind",
            "metric",
            "baseline",
            "current",
            "delta",
            "delta_percent",
            "direction",
            "result",
            "gate_policy",
        ),
    )


def _write_csv(path: Path, rows: list[dict[str, object]], headers: tuple[str, ...]) -> None:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({header: _csv_value(row.get(header)) for header in headers})
    path.write_text(buffer.getvalue(), encoding="utf-8")


def _csv_value(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True)
    return value


def _probe_phase_csv_rows(report: dict[str, object]) -> list[dict[str, object]]:
    probe_summary = report.get("probe_summary")
    if not isinstance(probe_summary, dict):
        return []
    rows: list[dict[str, object]] = []
    for side in ("baseline", "candidate"):
        side_summary = probe_summary.get(side)
        if not isinstance(side_summary, dict):
            continue
        rows.extend(_probe_summary_rows(side=side, scope="combined", summary=side_summary))
        for run_summary in _dict_list(side_summary.get("runs")):
            rows.extend(
                _probe_summary_rows(
                    side=side,
                    scope="run",
                    summary=run_summary,
                    run_id=str(run_summary.get("run_id") or ""),
                    run_kind=str(run_summary.get("run_kind") or ""),
                )
            )
    return rows


def _probe_summary_rows(
    *,
    side: str,
    scope: str,
    summary: dict[str, object],
    run_id: str = "",
    run_kind: str = "",
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for bucket in ("slowest_phases", "failed_phases", "skipped_phases", "fallback_phases"):
        for item in _dict_list(summary.get(bucket)):
            rows.append(
                {
                    "side": side,
                    "scope": scope,
                    "run_id": run_id or str(item.get("run_id") or ""),
                    "run_kind": run_kind,
                    "bucket": bucket,
                    "component": item.get("component"),
                    "phase": item.get("phase"),
                    "duration_ms": item.get("duration_ms"),
                    "status": item.get("status"),
                    "error_stage": item.get("error_stage"),
                    "error_code": item.get("error_code"),
                }
            )
    return rows


def _telemetry_csv_rows(report: dict[str, object]) -> list[dict[str, object]]:
    telemetry_summary = report.get("telemetry_summary")
    if not isinstance(telemetry_summary, dict):
        return []
    rows: list[dict[str, object]] = []
    for side in ("baseline", "candidate"):
        rows.extend(_dict_list(telemetry_summary.get(side)))
    return rows


def _model_memory_csv_rows(report: dict[str, object]) -> list[dict[str, object]]:
    model_memory_summary = report.get("model_memory_summary")
    if not isinstance(model_memory_summary, dict):
        return []
    rows: list[dict[str, object]] = []
    for side in ("baseline", "candidate"):
        rows.extend(_dict_list(model_memory_summary.get(side)))
    return rows


def _process_csv_rows(report: dict[str, object]) -> list[dict[str, object]]:
    process_attribution = report.get("process_attribution")
    if not isinstance(process_attribution, dict):
        return []
    rows: list[dict[str, object]] = []
    for side in ("baseline", "candidate"):
        for summary in _dict_list(process_attribution.get(side)):
            common = {
                "side": side,
                "run_id": summary.get("run_id"),
                "run_kind": summary.get("run_kind"),
            }
            for group in ("primary_runtime_process", "control_plane_process"):
                process = summary.get(group)
                if isinstance(process, dict) and process:
                    rows.append({**common, "group": group, **_process_csv_row(process)})
            for group in ("worker_processes", "external_provider_processes"):
                for process in _dict_list(summary.get(group)):
                    rows.append({**common, "group": group, **_process_csv_row(process)})
            process_tree_summary = summary.get("process_tree_summary")
            if isinstance(process_tree_summary, dict) and process_tree_summary:
                rows.append(
                    {
                        **common,
                        "group": "process_tree_summary",
                        "process_tree_summary": process_tree_summary,
                    }
                )
    return rows


def _process_csv_row(process: dict[str, object]) -> dict[str, object]:
    return {
        "pid": process.get("pid"),
        "name": process.get("name"),
        "role": process.get("role"),
        "port": process.get("port"),
        "bundle_prefix": process.get("bundle_prefix"),
        "peak_memory_bytes": process.get("peak_memory_bytes", process.get("memory_bytes")),
        "avg_cpu_percent": process.get("avg_cpu_percent", process.get("cpu_percent")),
        "sample_count": process.get("sample_count"),
    }


def _comparison_delta_csv_rows(report: dict[str, object]) -> list[dict[str, object]]:
    comparison = report.get("comparison")
    if not isinstance(comparison, dict):
        return []
    rows: list[dict[str, object]] = []
    for key, kind in (
        ("metric_deltas", "metric"),
        ("probe_deltas", "probe"),
        ("telemetry_deltas", "telemetry"),
    ):
        for row in _dict_list(comparison.get(key)):
            rows.append({"kind": kind, **row})
    return rows


def _render_run_summary_markdown(runs: object) -> list[str]:
    run_rows = _dict_list(runs)
    if not run_rows:
        return []
    lines = [
        "## Run Summary",
        "",
        "| Side | Run ID | Kind | Status | Duration ms | Artifact Root |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    for row in run_rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown_cell(row.get("side", "")),
                    _markdown_cell(row.get("run_id", "")),
                    _markdown_cell(row.get("run_kind", "")),
                    _markdown_cell(row.get("status", "")),
                    _markdown_cell(_format_value(row.get("duration_ms"))),
                    _markdown_cell(row.get("artifact_root", "")),
                ]
            )
            + " |"
        )
    lines.append("")
    return lines


def _render_gate_summary_markdown(gate_result: object) -> list[str]:
    if not isinstance(gate_result, dict):
        return []
    lines = [
        "## Gate Summary",
        "",
        f"- Overall Result: `{gate_result.get('overall_result', 'informational')}`",
        f"- Blocking Failures: `{len(_dict_list(gate_result.get('blocking_failures')))}`",
        f"- Informational Results: `{len(_dict_list(gate_result.get('informational_results')))}`",
        f"- Required Evidence Present: `{gate_result.get('required_evidence_present', False)}`",
        f"- Required Probe Phases Present: `{gate_result.get('required_probe_phases_present', False)}`",
        f"- Required Telemetry Present: `{gate_result.get('required_telemetry_present', False)}`",
        "",
    ]
    return lines


def _render_telemetry_summary_markdown(telemetry_summary: object) -> list[str]:
    if not isinstance(telemetry_summary, dict):
        return []
    lines = [
        "## Telemetry Summary",
        "",
        f"- Hardware: `{telemetry_summary.get('hardware_banner', 'Apple Silicon / macOS telemetry')}`",
        "",
        "| Side | Run ID | Status | Avg System W | Peak System W | Watts / Token | Failures |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    has_rows = False
    for side in ("baseline", "candidate"):
        for row in _dict_list(telemetry_summary.get(side)):
            has_rows = True
            failures = row.get("telemetry_failures")
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_cell(side),
                        _markdown_cell(row.get("run_id", "")),
                        _markdown_cell(row.get("collector_status", "")),
                        _markdown_cell(_format_value(row.get("average_system_power_w"))),
                        _markdown_cell(_format_value(row.get("peak_system_power_w"))),
                        _markdown_cell(_format_value(row.get("watts_per_output_token"))),
                        _markdown_cell(", ".join(str(item) for item in failures) if isinstance(failures, list) else ""),
                    ]
                )
                + " |"
            )
    if not has_rows:
        lines.append("| - | - | missing | - | - | - | telemetry_summary_missing |")
    lines.append("")
    return lines


def _render_model_memory_summary_markdown(model_memory_summary: object) -> list[str]:
    if not isinstance(model_memory_summary, dict):
        return []
    rows = [
        row
        for side in ("baseline", "candidate")
        for row in _dict_list(model_memory_summary.get(side))
    ]
    if not rows:
        return []
    lines = [
        "## Model Memory Summary",
        "",
        "| Side | Run ID | Model | Runtime | Loaded Model Resident | Registry Model Resident | Load RSS Delta | Scope |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown_cell(row.get("side", "")),
                    _markdown_cell(row.get("run_id", "")),
                    _markdown_cell(row.get("runtime_model_id", "")),
                    _markdown_cell(row.get("runtime_name") or row.get("runtime_kind", "")),
                    _markdown_cell(_format_value(row.get("loaded_model_estimated_resident_bytes"))),
                    _markdown_cell(_format_value(row.get("runtime_stats_model_resident_bytes"))),
                    _markdown_cell(_format_value(row.get("load_rss_delta_bytes"))),
                    _markdown_cell(row.get("measurement_scope", "")),
                ]
            )
            + " |"
        )
    lines.append("")
    return lines


def _render_reproducibility_warnings_markdown(report: dict[str, object]) -> list[str]:
    warnings = [
        str(item)
        for item in report.get("reproducibility_warnings", [])
        if str(item).strip()
    ] if isinstance(report.get("reproducibility_warnings"), list) else []
    if not warnings:
        return []
    lines = ["", "## Reproducibility Warnings", ""]
    for warning in warnings:
        lines.append(f"- `{_markdown_cell(warning)}`")
    lines.append("")
    return lines


def _render_known_gaps_markdown(report: dict[str, object]) -> list[str]:
    known_gaps = [str(item) for item in report.get("known_gaps", []) if str(item).strip()] if isinstance(report.get("known_gaps"), list) else []
    instrumentation_gaps = [str(item) for item in report.get("instrumentation_gaps", []) if str(item).strip()] if isinstance(report.get("instrumentation_gaps"), list) else []
    if not known_gaps and not instrumentation_gaps:
        return []
    lines = ["", "## Known Gaps", ""]
    for gap in known_gaps:
        lines.append(f"- `{_markdown_cell(gap)}`")
    for gap in instrumentation_gaps:
        lines.append(f"- `{_markdown_cell(gap)}`")
    lines.append("")
    return lines


def _render_artifacts_markdown(artifacts: object) -> list[str]:
    if not isinstance(artifacts, dict):
        return []
    artifact_rows = [
        ("Report JSON", artifacts.get("report_json_path")),
        ("Markdown", artifacts.get("markdown_report_path")),
        ("Probe Timeline", artifacts.get("probe_timeline_path")),
        ("Telemetry JSONL", artifacts.get("telemetry_jsonl_path")),
        ("Coverage", artifacts.get("coverage_path")),
    ]
    csv_paths = artifacts.get("csv_export_paths")
    if isinstance(csv_paths, dict):
        for name, path in sorted(csv_paths.items()):
            artifact_rows.append((f"CSV {name}", path))
    artifact_rows = [(label, path) for label, path in artifact_rows if str(path or "").strip()]
    if not artifact_rows:
        return []
    lines = ["", "## Artifacts", ""]
    for label, path in artifact_rows:
        lines.append(f"- {label}: `{_markdown_cell(path)}`")
    lines.append("")
    return lines


def _is_improvement(row: dict[str, object]) -> bool:
    delta = _float_or_none(row.get("delta"))
    if delta is None:
        return False
    direction = str(row.get("direction") or "")
    if direction == "lower_is_better":
        return delta < 0
    if direction == "higher_is_better":
        return delta > 0
    return False


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _int_or_none(value: object) -> int | None:
    value_type = type(value)
    if value_type is int or value_type is bool:
        return int(value)
    if value_type is float:
        return int(value)
    if isinstance(value, str):
        stripped_value = value.strip()
        if stripped_value:
            try:
                return int(float(stripped_value))
            except ValueError:
                return None
    return None


def _collect_metrics(bundle: dict[str, object]) -> dict[str, object]:
    metrics: dict[str, object] = {}
    label_cache: dict[_BenchmarkLabelCacheKey, str] = {}
    _collect_runtime_metadata(
        metrics,
        bundle.get("benchmark_jobs", []),
        prefix="bench.runtime",
    )
    _collect_runtime_metadata(
        metrics,
        bundle.get("benchmark_matrix_jobs", []),
        prefix="bench.matrix.runtime",
    )
    _collect_runtime_metadata(
        metrics,
        bundle.get("evaluation_jobs", []),
        prefix="eval.runtime",
    )
    for result in _dict_rows(bundle.get("benchmark_results", [])):
        for metric in _dict_rows(result.get("metrics", [])):
            name = str(metric.get("name", "")).strip()
            value = _float_or_none(metric.get("value"))
            if name and value is not None:
                metrics[name] = value
    _collect_benchmark_probe_metrics(
        metrics,
        bundle.get("benchmark_context_rows", []),
        prefix="bench.context",
        label_cache=label_cache,
    )
    _collect_benchmark_probe_metrics(
        metrics,
        bundle.get("benchmark_batch_rows", []),
        prefix="bench.batch",
        label_cache=label_cache,
    )
    for row in _dict_rows(bundle.get("benchmark_matrix_summary_rows", [])):
        label = _matrix_label(row, label_cache=label_cache)
        for key in _MATRIX_SUMMARY_METRIC_KEYS:
            value = _float_or_none(row.get(key))
            if value is not None:
                metrics[f"bench.matrix.{label}.{key}"] = value
    _collect_benchmark_probe_metrics(
        metrics,
        bundle.get("benchmark_matrix_request_rows", []),
        prefix="bench.matrix.request",
        label_cache=label_cache,
    )
    for row in _dict_rows(bundle.get("evaluation_summary_rows", [])):
        suite_id = str(row.get("suite_id", "")).strip() or "suite"
        score_name = str(row.get("primary_score_name", "")).strip() or "primary_score"
        score_value = _float_or_none(row.get("primary_score_value"))
        if score_value is not None:
            metrics[f"eval.{suite_id}.{score_name}"] = score_value
        for key in _EVALUATION_SUMMARY_METRIC_KEYS:
            value = _float_or_none(row.get(key))
            if value is not None:
                metrics[f"eval.{suite_id}.{key}"] = value
    _collect_evaluation_sample_probe_metrics(metrics, bundle.get("evaluation_samples", []))
    _collect_run_evidence_probe_metrics(metrics, bundle.get("run_evidence", []))
    _collect_run_evidence_telemetry_metrics(metrics, bundle.get("run_evidence", []))
    _collect_run_evidence_model_memory_metrics(metrics, bundle.get("run_evidence", []))
    return metrics


def _build_metric_row(
    *,
    metric_name: str,
    baseline: object | None,
    candidate: object | None,
) -> dict[str, object]:
    direction = _metric_direction(metric_name)
    if baseline is None or candidate is None:
        return {
            "metric": metric_name,
            "baseline": baseline,
            "candidate": candidate,
            "delta": None,
            "delta_pct": None,
            "direction": direction,
            "status": "missing",
        }
    baseline_type = type(baseline)
    if baseline_type is float:
        baseline_number = baseline
    elif baseline_type is int or baseline_type is bool:
        baseline_number = float(baseline)
    else:
        baseline_number = _float_or_none(baseline)
    candidate_type = type(candidate)
    if candidate_type is float:
        candidate_number = candidate
    elif candidate_type is int or candidate_type is bool:
        candidate_number = float(candidate)
    else:
        candidate_number = _float_or_none(candidate)
    if baseline_number is None or candidate_number is None:
        return {
            "metric": metric_name,
            "baseline": baseline,
            "candidate": candidate,
            "delta": None,
            "delta_pct": None,
            "direction": "metadata",
            "status": "ok" if str(baseline) == str(candidate) else "not_comparable",
        }
    delta = candidate_number - baseline_number
    delta_pct = (delta / abs(baseline_number) * 100.0) if baseline_number != 0 else None
    if direction == "neutral":
        status = "ok" if round(delta, 6) == 0 else "not_comparable"
    else:
        status = "ok"
    if direction == "lower_is_better" and (
        (delta_pct is not None and delta_pct > _WARNING_THRESHOLD_PCT)
        or (baseline_number == 0 and candidate_number > baseline_number)
    ):
        status = "warning"
    elif direction == "higher_is_better" and (
        (delta_pct is not None and delta_pct < -_WARNING_THRESHOLD_PCT)
        or (baseline_number == 0 and candidate_number < baseline_number)
    ):
        status = "warning"
    return {
        "metric": metric_name,
        "baseline": baseline_number,
        "candidate": candidate_number,
        "delta": round(delta, 6),
        "delta_pct": round(delta_pct, 6) if delta_pct is not None else None,
        "direction": direction,
        "status": status,
    }


@lru_cache(maxsize=None)
def _metric_direction(metric_name: str) -> str:
    return _metric_key_direction(metric_name.rsplit(".", maxsplit=1)[-1])


@lru_cache(maxsize=None)
def _metric_key_direction(metric_key: str) -> str:
    known_direction = _METRIC_DIRECTION_BY_KEY.get(metric_key)
    if known_direction is not None:
        return known_direction
    for fragment in _LOWER_IS_BETTER_METRIC_FRAGMENTS:
        if fragment in metric_key:
            return "lower_is_better"
    for fragment in _HIGHER_IS_BETTER_METRIC_FRAGMENTS:
        if fragment in metric_key:
            return "higher_is_better"
    return "neutral"


def _collect_runtime_metadata(
    metrics: dict[str, object],
    jobs: object,
    *,
    prefix: str,
) -> None:
    values_by_key: dict[str, set[str]] = {}
    for job in _dict_rows(jobs):
        parameters = job.get("parameters", {})
        if not isinstance(parameters, dict):
            continue
        for key in _RUNTIME_PARAMETER_KEYS:
            value = str(parameters.get(key, "")).strip()
            if value:
                values_by_key.setdefault(key, set()).add(value)
    for key in _RUNTIME_PARAMETER_KEYS:
        values = values_by_key.get(key)
        if values:
            metrics[f"{prefix}.{key}"] = ",".join(sorted(values))


def _collect_benchmark_probe_metrics(
    metrics: dict[str, object],
    rows: object,
    *,
    prefix: str,
    label_cache: dict[_BenchmarkLabelCacheKey, str] | None = None,
) -> None:
    aggregate_pairs: dict[_ProbeAggregateKey, _NumericAggregate] = {}
    matrix_label_cache: dict[tuple[object, object, object, object, object], str] = {}
    for row in _dict_rows(rows):
        label = ""
        for key, raw_value in row.items():
            if key not in _REQUEST_PROBE_KEY_SET:
                continue
            raw_value_type = type(raw_value)
            if raw_value_type is float:
                value = raw_value
            elif raw_value_type is int or raw_value_type is bool:
                value = float(raw_value)
            else:
                value = _float_or_none(raw_value)
            if value is not None:
                if not label:
                    label = _benchmark_probe_label(
                        row,
                        label_cache=label_cache,
                        matrix_label_cache=matrix_label_cache,
                    )
                _update_probe_aggregate_pairs(
                    aggregate_pairs,
                    label=label,
                    key=key,
                    value=value,
                )
    metrics.update(_finalize_probe_aggregates(aggregate_pairs, prefix=prefix))


def _collect_evaluation_sample_probe_metrics(
    metrics: dict[str, object],
    rows: object,
) -> None:
    aggregates_by_suite_and_key: dict[tuple[str, str], _NumericAggregate] = {}
    failure_stage_counts: dict[tuple[str, str], int] = {}
    for row in _dict_rows(rows):
        suite_id = str(row.get("suite_id", "")).strip() or "suite"
        for key in _EVALUATION_SAMPLE_PROBE_KEYS:
            if key not in row:
                continue
            raw_value = row[key]
            raw_value_type = type(raw_value)
            if raw_value_type is float:
                value = raw_value
            elif raw_value_type is int or raw_value_type is bool:
                value = float(raw_value)
            else:
                value = _float_or_none(raw_value)
            if value is not None:
                aggregate_key = (suite_id, key)
                aggregates_by_suite_and_key[aggregate_key] = _update_numeric_aggregate(
                    aggregates_by_suite_and_key.get(aggregate_key),
                    value,
                )
        failure_stage = str(row.get("failure_stage", "")).strip()
        if failure_stage:
            failure_stage_counts[(suite_id, failure_stage)] = (
                failure_stage_counts.get((suite_id, failure_stage), 0) + 1
            )
    for (suite_id, key), aggregate in aggregates_by_suite_and_key.items():
        total, count = aggregate
        metrics[f"eval.sample.{suite_id}.{key}_mean"] = total / count
    for (suite_id, failure_stage), count in failure_stage_counts.items():
        metrics[f"eval.sample.{suite_id}.failure_stage.{failure_stage}.failure_count"] = float(count)


def _collect_run_evidence_probe_metrics(metrics: dict[str, object], rows: object) -> None:
    aggregates_by_key: dict[tuple[str, str, str], _NumericAggregate] = {}
    counts_by_key: dict[tuple[str, str, str, str], int] = {}
    for evidence in _dict_rows(rows):
        run_kind = str(evidence.get("run_kind", "")).strip() or "run"
        for probe in _dict_rows(evidence.get("probe_timeline", [])):
            component = str(probe.get("component", "")).strip() or "component"
            phase = str(probe.get("phase", "")).strip() or "phase"
            attributes = probe.get("attributes")
            if not isinstance(attributes, dict):
                attributes = {}
            probe_kind = str(attributes.get("probe_kind", "")).strip()
            if probe_kind == "sample_detail":
                continue
            duration = _float_or_none(probe.get("duration_ms"))
            if duration is not None:
                aggregate_key = (run_kind, component, phase)
                aggregates_by_key[aggregate_key] = _update_numeric_aggregate(
                    aggregates_by_key.get(aggregate_key),
                    duration,
                )
            if probe_kind == "aggregate_summary":
                for status, attribute_key in (
                    ("failed", "failed_count"),
                    ("skipped", "skipped_count"),
                ):
                    count = _float_or_none(attributes.get(attribute_key))
                    if count:
                        count_key = (run_kind, component, phase, status)
                        counts_by_key[count_key] = counts_by_key.get(count_key, 0) + int(count)
                if phase in {"fallback_enter", "fallback_exit"}:
                    count = _float_or_none(attributes.get("fallback_sample_count"))
                    if count:
                        status = str(probe.get("status", "")).strip() or "completed"
                        count_key = (run_kind, component, phase, status)
                        counts_by_key[count_key] = counts_by_key.get(count_key, 0) + int(count)
                continue
            status = str(probe.get("status", "")).strip()
            if status in {"failed", "skipped"} or phase in {"fallback_enter", "fallback_exit"}:
                count_key = (run_kind, component, phase, status or "completed")
                counts_by_key[count_key] = counts_by_key.get(count_key, 0) + 1
    for (run_kind, component, phase), aggregate in aggregates_by_key.items():
        total, count = aggregate
        metrics[f"probe.{run_kind}.{component}.{phase}.duration_ms_mean"] = total / count
    for (run_kind, component, phase, status), count in counts_by_key.items():
        metrics[f"probe.{run_kind}.{component}.{phase}.{status}_count"] = float(count)


def _collect_run_evidence_telemetry_metrics(metrics: dict[str, object], rows: object) -> None:
    aggregates_by_key: dict[tuple[str, str], _NumericAggregate] = {}
    failure_counts: dict[str, int] = {}
    for evidence in _dict_rows(rows):
        run_kind = str(evidence.get("run_kind", "")).strip() or "run"
        telemetry = evidence.get("telemetry_summary")
        if not isinstance(telemetry, dict):
            continue
        failures = telemetry.get("telemetry_failures")
        if isinstance(failures, list) and failures:
            failure_counts[run_kind] = failure_counts.get(run_kind, 0) + len(failures)
        for key, raw_value in telemetry.items():
            if key in {"schema_version", "collector_status", "time_series_path", "telemetry_failures", "thermal_events", "process_attribution"}:
                continue
            value = _float_or_none(raw_value)
            if value is None:
                continue
            aggregate_key = (run_kind, key)
            aggregates_by_key[aggregate_key] = _update_numeric_aggregate(
                aggregates_by_key.get(aggregate_key),
                value,
            )
    for (run_kind, key), aggregate in aggregates_by_key.items():
        total, count = aggregate
        metrics[f"telemetry.{run_kind}.{key}_mean"] = total / count
    for run_kind, count in failure_counts.items():
        metrics[f"telemetry.{run_kind}.telemetry_failure_count"] = float(count)


def _collect_run_evidence_model_memory_metrics(metrics: dict[str, object], rows: object) -> None:
    aggregates_by_key: dict[tuple[str, str], _NumericAggregate] = {}
    for evidence in _dict_rows(rows):
        run_kind = str(evidence.get("run_kind", "")).strip() or "run"
        memory = evidence.get("model_memory_summary")
        if not isinstance(memory, dict):
            continue
        for key, raw_value in memory.items():
            if key in {
                "runtime_model_handle",
                "runtime_model_id",
                "runtime_kind",
                "runtime_name",
                "measurement_scope",
            }:
                continue
            value = _float_or_none(raw_value)
            if value is None:
                continue
            aggregate_key = (run_kind, key)
            aggregates_by_key[aggregate_key] = _update_numeric_aggregate(
                aggregates_by_key.get(aggregate_key),
                value,
            )
    for (run_kind, key), aggregate in aggregates_by_key.items():
        total, count = aggregate
        metrics[f"model_memory.{run_kind}.{key}_mean"] = total / count


def _update_numeric_aggregate(
    aggregate: _NumericAggregate | None,
    value: float,
) -> _NumericAggregate:
    if aggregate is None:
        return (value, 1)
    return (aggregate[0] + value, aggregate[1] + 1)


def _update_probe_aggregate_pairs(
    aggregate_pairs: dict[_ProbeAggregateKey, _NumericAggregate],
    *,
    label: str,
    key: str,
    value: float,
) -> None:
    aggregate_key = (label, key)
    aggregate_pairs[aggregate_key] = _update_numeric_aggregate(aggregate_pairs.get(aggregate_key), value)


def _update_probe_aggregates_by_label(
    aggregates_by_label: dict[str, dict[str, _NumericAggregate]],
    *,
    label: str,
    key: str,
    value: float,
) -> None:
    aggregates_by_key = aggregates_by_label.get(label)
    if aggregates_by_key is None:
        aggregates_by_key = {}
        aggregates_by_label[label] = aggregates_by_key
    aggregates_by_key[key] = _update_numeric_aggregate(aggregates_by_key.get(key), value)


def _finalize_probe_aggregates(
    aggregate_pairs: dict[_ProbeAggregateKey, _NumericAggregate],
    *,
    prefix: str,
) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for (label, key), aggregate in aggregate_pairs.items():
        suffix, value = _finalize_numeric_aggregate(key, aggregate)
        metrics[f"{prefix}.{label}.{key}_{suffix}"] = value
    return metrics


def _finalize_numeric_aggregate(
    key: str,
    aggregate: _NumericAggregate | None,
) -> tuple[str, float]:
    if aggregate is None:
        if key in _RATE_PROBE_KEYS:
            return ("rate", 0.0)
        if key in _COUNT_PROBE_KEYS:
            return ("sum", 0.0)
        return ("mean", 0.0)
    total, count = aggregate
    if key in _COUNT_PROBE_KEYS:
        return ("sum", total)
    if key in _RATE_PROBE_KEYS:
        return ("rate", total / count)
    return ("mean", total / count)


def _aggregate_probe_values(key: str, values: list[float]) -> tuple[str, float]:
    aggregate: _NumericAggregate | None = None
    for value in values:
        aggregate = _update_numeric_aggregate(aggregate, value)
    return _finalize_numeric_aggregate(key, aggregate)


def _benchmark_probe_label(
    row: dict[str, object],
    label_cache: dict[_BenchmarkLabelCacheKey, str] | None = None,
    *,
    matrix_label_cache: dict[tuple[object, object, object, object, object], str] | None = None,
) -> str:
    if "cell_id" in row or ("suite_id" in row and "concurrency_level" in row):
        if matrix_label_cache is not None:
            cache_key = (
                row.get("suite_id", "suite"),
                row.get("context_length", 0),
                row.get("generation_length", 0),
                row.get("batch_size", 0),
                row.get("concurrency_level", 0),
            )
            try:
                return matrix_label_cache[cache_key]
            except KeyError:
                label = _matrix_label(row, label_cache=label_cache)
                matrix_label_cache[cache_key] = label
                return label
            except TypeError:
                pass
        return _matrix_label(row, label_cache=label_cache)
    key = (
        "bench",
        str(row.get("suite", row.get("suite_id", "suite"))),
        str(row.get("context_length", 0)),
        str(row.get("generation_length", 0)),
        str(row.get("batch_size", 0)),
        "",
    )
    return _cached_benchmark_label(key, label_cache=label_cache)


def _matrix_label(
    row: dict[str, object],
    label_cache: dict[_BenchmarkLabelCacheKey, str] | None = None,
) -> str:
    key = (
        "matrix",
        str(row.get("suite_id", "suite")),
        str(row.get("context_length", 0)),
        str(row.get("generation_length", 0)),
        str(row.get("batch_size", 0)),
        str(row.get("concurrency_level", 0)),
    )
    return _cached_benchmark_label(key, label_cache=label_cache)


def _cached_benchmark_label(
    key: _BenchmarkLabelCacheKey,
    *,
    label_cache: dict[_BenchmarkLabelCacheKey, str] | None,
) -> str:
    if label_cache is None:
        return _build_benchmark_label(key)
    cached = label_cache.get(key)
    if cached is not None:
        return cached
    label = _build_benchmark_label(key)
    label_cache[key] = label
    return label


def _build_benchmark_label(key: _BenchmarkLabelCacheKey) -> str:
    kind, suite, context_length, generation_length, batch_size, concurrency_level = key
    parts = [
        suite.replace(" ", "_"),
        f"ctx{_label_part(context_length)}",
        f"gen{_label_part(generation_length)}",
        f"b{_label_part(batch_size)}",
    ]
    if kind == "matrix":
        parts.append(f"c{_label_part(concurrency_level)}")
    return ".".join(parts)


def _label_part(value: object) -> str:
    if isinstance(value, (int, float, bool)):
        return str(value)
    return str(value).replace(" ", "_")


def _report_rows(report: dict[str, object]) -> Iterator[dict[str, object]]:
    rows = report.get("rows", [])
    if not isinstance(rows, list):
        return
    for row in rows:
        if isinstance(row, dict):
            yield row


def _dict_rows(value: object) -> Iterator[dict[str, object]]:
    if not isinstance(value, list):
        return iter(())
    return (row for row in value if isinstance(row, dict))


def _run_evidence_rows(bundle: dict[str, object]) -> list[dict[str, object]]:
    return list(_dict_rows(bundle.get("run_evidence", [])))


def _render_probe_summary_markdown(probe_summary: dict[str, object]) -> list[str]:
    lines = ["", "## Probe Summary", ""]
    for side in ("baseline", "candidate"):
        summary = probe_summary.get(side)
        if not isinstance(summary, dict):
            continue
        lines.append(f"### {side.title()}")
        lines.append("")
        lines.append(f"- Probes: `{summary.get('probe_count', 0)}`")
        lines.append(f"- Failed phases: `{len(summary.get('failed_phases', []) if isinstance(summary.get('failed_phases'), list) else [])}`")
        lines.append(f"- Skipped phases: `{len(summary.get('skipped_phases', []) if isinstance(summary.get('skipped_phases'), list) else [])}`")
        lines.append(f"- Fallback phases: `{len(summary.get('fallback_phases', []) if isinstance(summary.get('fallback_phases'), list) else [])}`")
        slowest = summary.get("slowest_phases")
        if isinstance(slowest, list) and slowest:
            lines.extend(["", "| Component | Phase | Duration ms | Status |", "| --- | --- | ---: | --- |"])
            for row in slowest[:5]:
                if not isinstance(row, dict):
                    continue
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            _markdown_cell(row.get("component", "")),
                            _markdown_cell(row.get("phase", "")),
                            _markdown_cell(_format_value(row.get("duration_ms"))),
                            _markdown_cell(row.get("status", "")),
                        ]
                    )
                    + " |"
                )
        lines.append("")
    return lines


def _float_or_none(value: object) -> float | None:
    value_type = type(value)
    if value_type is float:
        return value
    if value_type is int or value_type is bool:
        return float(value)
    if isinstance(value, str):
        stripped_value = value.strip()
        if stripped_value:
            try:
                return float(stripped_value)
            except ValueError:
                return None
    return None


def _format_value(value: object) -> str:
    if value is None:
        return "-"
    numeric = _float_or_none(value)
    if numeric is None:
        return str(value)
    return f"{numeric:.4f}"


def _format_delta(row: dict[str, object]) -> str:
    delta = row.get("delta")
    delta_pct = row.get("delta_pct")
    if delta is None:
        return "-"
    delta_value = float(delta)
    if delta_pct is None:
        return f"{delta_value:+.4f}"
    return f"{delta_value:+.4f} ({float(delta_pct):+.2f}%)"


def _markdown_cell(value: object) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|").replace("`", "\\`")
