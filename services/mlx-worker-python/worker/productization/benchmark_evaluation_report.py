from __future__ import annotations

from collections.abc import Iterator
import json
from pathlib import Path
from typing import Any

_COMMENT_MARKER = "<!-- melix-benchmark-evaluation-report -->"
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
_EVALUATION_SAMPLE_PROBE_KEY_SET = frozenset(_EVALUATION_SAMPLE_PROBE_KEYS)
_LOWER_IS_BETTER_METRIC_FRAGMENTS = (
    "latency",
    "ttft",
    "_ms",
    "duration_seconds",
    "memory",
    "bytes",
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

_NumericAggregate = tuple[float, int]
_BenchmarkLabelCacheKey = tuple[str, str, str, str, str, str]


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
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"report input could not be decoded: {input_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"report input must be a JSON object: {input_path}")
    return payload


def build_benchmark_evaluation_report(
    *,
    baseline: dict[str, object],
    candidate: dict[str, object],
) -> dict[str, object]:
    baseline_metrics = _collect_metrics(baseline)
    candidate_metrics = _collect_metrics(candidate)
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
        match row["status"]:
            case "warning":
                warning_count += 1
            case "missing":
                missing_count += 1
            case "not_comparable":
                not_comparable_count += 1
    status = "warning" if warning_count else "ok"
    if missing_count and status == "ok":
        status = "missing"
    if not_comparable_count and status == "ok":
        status = "not_comparable"
    return {
        "schema_version": "melix.benchmark_evaluation_report.v1",
        "summary": {
            "status": status,
            "metric_count": len(rows),
            "warning_count": warning_count,
            "missing_count": missing_count,
            "not_comparable_count": not_comparable_count,
        },
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
        "| Metric | Baseline | Candidate | Delta | Status |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
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
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown_report(report), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


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
        for key in (
            "request_latency_mean_ms",
            "request_latency_p95_ms",
            "ttft_mean_ms",
            "ttft_p95_ms",
            "throughput_tokens_per_second",
            "success_rate",
            "failed_count",
        ):
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
        for key in ("failure_count", "duration_seconds"):
            value = _float_or_none(row.get(key))
            if value is not None:
                metrics[f"eval.{suite_id}.{key}"] = value
    _collect_evaluation_sample_probe_metrics(metrics, bundle.get("evaluation_samples", []))
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
    baseline_number = _float_or_none(baseline)
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


def _metric_direction(metric_name: str) -> str:
    metric_key = metric_name.rsplit(".", maxsplit=1)[-1]
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
    values_by_key: dict[str, set[str]] = {key: set() for key in _RUNTIME_PARAMETER_KEYS}
    for job in _dict_rows(jobs):
        parameters = job.get("parameters", {})
        if not isinstance(parameters, dict):
            continue
        for key in _RUNTIME_PARAMETER_KEYS:
            value = str(parameters.get(key, "")).strip()
            if value:
                values_by_key[key].add(value)
    for key, values in values_by_key.items():
        if values:
            metrics[f"{prefix}.{key}"] = ",".join(sorted(values))


def _collect_benchmark_probe_metrics(
    metrics: dict[str, object],
    rows: object,
    *,
    prefix: str,
    label_cache: dict[_BenchmarkLabelCacheKey, str] | None = None,
) -> None:
    aggregates_by_label: dict[str, dict[str, _NumericAggregate]] = {}
    for row in _dict_rows(rows):
        label = ""
        for key, raw_value in row.items():
            if key not in _REQUEST_PROBE_KEY_SET:
                continue
            if isinstance(raw_value, (int, float)):
                value = float(raw_value)
            else:
                value = _float_or_none(raw_value)
            if value is not None:
                if not label:
                    label = _benchmark_probe_label(row, label_cache=label_cache)
                _update_probe_aggregates_by_label(
                    aggregates_by_label,
                    label=label,
                    key=key,
                    value=value,
                )
    for label, aggregates_by_key in aggregates_by_label.items():
        for key, aggregate in aggregates_by_key.items():
            suffix, value = _finalize_numeric_aggregate(key, aggregate)
            metrics[f"{prefix}.{label}.{key}_{suffix}"] = value


def _collect_evaluation_sample_probe_metrics(
    metrics: dict[str, object],
    rows: object,
) -> None:
    aggregates_by_suite_and_key: dict[tuple[str, str], _NumericAggregate] = {}
    failure_stage_counts: dict[tuple[str, str], int] = {}
    for row in _dict_rows(rows):
        suite_id = str(row.get("suite_id", "")).strip() or "suite"
        for key, raw_value in row.items():
            if key not in _EVALUATION_SAMPLE_PROBE_KEY_SET:
                continue
            if isinstance(raw_value, (int, float)):
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
        _, value = _finalize_numeric_aggregate(key, aggregate)
        metrics[f"eval.sample.{suite_id}.{key}_mean"] = value
    for (suite_id, failure_stage), count in failure_stage_counts.items():
        metrics[f"eval.sample.{suite_id}.failure_stage.{failure_stage}.failure_count"] = float(count)


def _update_numeric_aggregate(
    aggregate: _NumericAggregate | None,
    value: float,
) -> _NumericAggregate:
    if aggregate is None:
        return (value, 1)
    return (aggregate[0] + value, aggregate[1] + 1)


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


def _float_or_none(value: object) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
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
