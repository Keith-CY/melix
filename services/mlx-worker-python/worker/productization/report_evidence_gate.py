from __future__ import annotations

import heapq
import json
from functools import lru_cache
from pathlib import Path
from typing import AbstractSet

from worker.productization.benchmark_evaluation_report import validate_report_payload

REPORT_EVIDENCE_GATE_SCHEMA_VERSION = "melix.report_evidence_gate.v1"
_PROBE_PHASE_BUCKETS = ("slowest_phases", "failed_phases", "skipped_phases", "fallback_phases")
_PROBE_PHASE_SIDES = ("baseline", "candidate")

DEFAULT_RELEASE_EVIDENCE_MATRIX: dict[str, dict[str, object]] = {
    "serving_benchmark": {
        "run_kinds": ("serving_benchmark",),
        "description": "Serving benchmark report evidence is present.",
    },
    "dialogue_event_evaluation": {
        "run_kinds": ("evaluation", "dialogue_evaluation", "event_extraction"),
        "description": "Dialogue or event evaluation report evidence is present.",
    },
    "adapter_check": {
        "metric_prefixes": ("adapter.",),
        "target_fields": ("adapter_id", "adapter_snapshot"),
        "description": "Adapter check evidence is present.",
    },
    "runtime_check": {
        "probe_phases": ("runtime_prepare", "model_load", "decode"),
        "description": "Runtime probe evidence is present.",
    },
}


def load_report_payload(path: str | Path) -> dict[str, object]:
    report_path = path if isinstance(path, Path) else Path(path)
    try:
        payload = json.loads(report_path.read_bytes())
    except json.JSONDecodeError as exc:
        raise ValueError(f"report JSON could not be decoded: {report_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"report JSON must be an object: {report_path}")
    return payload


def build_report_evidence_gate(
    report_paths: list[str | Path],
    *,
    require_release_matrix: bool = False,
    require_hardware_telemetry: bool = False,
    matrix: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    active_matrix = matrix or DEFAULT_RELEASE_EVIDENCE_MATRIX
    reports = [
        _analyze_report(
            path=Path(path),
            report=load_report_payload(path),
            require_hardware_telemetry=require_hardware_telemetry,
            matrix=active_matrix,
        )
        for path in report_paths
    ]
    matrix_rows = _release_matrix_rows(reports, active_matrix)
    blocking_failures = [
        failure
        for report in reports
        for failure in _dict_list(report.get("blocking_failures"))
    ]
    if require_release_matrix:
        for row in matrix_rows:
            if row.get("required") and not row.get("present"):
                blocking_failures.append(
                    {
                        "source": "release_matrix",
                        "role": row.get("role"),
                        "message": f"release evidence matrix role is missing: {row.get('role')}",
                    }
                )
    known_gaps = sorted(
        {
            str(gap)
            for report in reports
            for gap in report.get("known_gaps", [])
            if str(gap).strip()
        }
    )
    informational_results = [
        result
        for report in reports
        for result in _dict_list(report.get("informational_results"))
    ]
    passed = not blocking_failures
    return {
        "schema_version": REPORT_EVIDENCE_GATE_SCHEMA_VERSION,
        "passed": passed,
        "overall_result": "pass" if passed else "fail",
        "require_release_matrix": require_release_matrix,
        "require_hardware_telemetry": require_hardware_telemetry,
        "release_matrix": matrix_rows,
        "reports": reports,
        "blocking_failures": blocking_failures,
        "informational_results": informational_results,
        "known_gaps": known_gaps,
        "pr_evidence": {
            "report_json_paths": [str(report.get("path", "")) for report in reports],
            "markdown_report_paths": [
                str(report.get("markdown_report_path", ""))
                for report in reports
                if str(report.get("markdown_report_path", "")).strip()
            ],
        },
    }


def render_pr_evidence_markdown(gate_report: dict[str, object]) -> str:
    lines = [
        "# Melix Report Evidence Gate",
        "",
        f"- Overall Result: `{gate_report.get('overall_result', 'fail')}`",
        f"- Blocking Failures: `{len(_dict_list(gate_report.get('blocking_failures')))}`",
        f"- Informational Results: `{len(_dict_list(gate_report.get('informational_results')))}`",
        "",
        "## Report Artifacts",
        "",
    ]
    pr_evidence = gate_report.get("pr_evidence")
    if isinstance(pr_evidence, dict):
        for path in pr_evidence.get("report_json_paths", []):
            lines.append(f"- Report JSON: `{path}`")
        for path in pr_evidence.get("markdown_report_paths", []):
            lines.append(f"- Markdown Report: `{path}`")
    lines.extend(["", "## Release Matrix", ""])
    lines.append("| Role | Required | Present | Evidence IDs |")
    lines.append("| --- | --- | --- | --- |")
    for row in _dict_list(gate_report.get("release_matrix")):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("role", "")),
                    str(row.get("required", "")),
                    str(row.get("present", "")),
                    ", ".join(str(item) for item in row.get("evidence_ids", [])),
                ]
            )
            + " |"
        )
    failures = _dict_list(gate_report.get("blocking_failures"))
    if failures:
        lines.extend(["", "## Blocking Failures", ""])
        for failure in failures:
            lines.append(f"- `{failure.get('message', failure)}`")
    known_gaps = [str(gap) for gap in gate_report.get("known_gaps", []) if str(gap).strip()]
    if known_gaps:
        lines.extend(["", "## Known Gaps", ""])
        for gap in known_gaps:
            lines.append(f"- `{gap}`")
    lines.append("")
    return "\n".join(lines)


def write_report_evidence_gate_outputs(
    gate_report: dict[str, object],
    output_dir: str | Path,
) -> dict[str, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "report-evidence-gate.json"
    markdown_path = root / "pr-evidence.md"
    json_path.write_text(json.dumps(gate_report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_pr_evidence_markdown(gate_report), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def _analyze_report(
    *,
    path: Path,
    report: dict[str, object],
    require_hardware_telemetry: bool,
    matrix: dict[str, dict[str, object]],
) -> dict[str, object]:
    validation_errors = validate_report_payload(report)
    gate_result = report.get("gate_result") if isinstance(report.get("gate_result"), dict) else {}
    artifacts = report.get("artifacts") if isinstance(report.get("artifacts"), dict) else {}
    telemetry_failures = _telemetry_failures(report)
    blocking_failures = [
        {
            "source": "report_validation",
            "report_id": report.get("report_id", ""),
            "path": str(path),
            "message": error,
        }
        for error in validation_errors
    ]
    for row in _dict_list(gate_result.get("blocking_failures")):
        blocking_failures.append(
            {
                "source": "gate_metric",
                "report_id": report.get("report_id", ""),
                "path": str(path),
                "metric": row.get("metric"),
                "message": f"gate metric failed: {row.get('metric')}",
                "row": row,
            }
        )
    if require_hardware_telemetry:
        for failure in telemetry_failures:
            blocking_failures.append(
                {
                    "source": "hardware_telemetry",
                    "report_id": report.get("report_id", ""),
                    "path": str(path),
                    "message": f"hardware telemetry failure: {failure}",
                }
            )
    source_evidence_ids = report.get("source_evidence_ids")
    known_gaps = report.get("known_gaps")
    return {
        "path": str(path),
        "report_id": report.get("report_id", ""),
        "report_kind": report.get("report_kind", ""),
        "source_evidence_ids": list(source_evidence_ids)
        if isinstance(source_evidence_ids, list)
        else [],
        "markdown_report_path": artifacts.get("markdown_report_path", ""),
        "validation_errors": validation_errors,
        "gate_result": gate_result.get("overall_result", "fail"),
        "blocking_failures": blocking_failures,
        "informational_results": _dict_list(gate_result.get("informational_results")),
        "known_gaps": list(known_gaps) if isinstance(known_gaps, list) else [],
        "telemetry_failures": telemetry_failures,
        "slowest_probe_phases": _slowest_probe_phases(report),
        "evidence_validity_metrics": gate_result.get("evidence_validity_metrics", {})
        if isinstance(gate_result.get("evidence_validity_metrics"), dict)
        else {},
        "release_matrix_roles": _report_matrix_roles(report, matrix),
    }


def _release_matrix_rows(
    reports: list[dict[str, object]],
    matrix: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    evidence_by_role: dict[str, set[str]] = {}
    for report in reports:
        roles = report.get("release_matrix_roles")
        source_evidence_ids = report.get("source_evidence_ids", [])
        if (
            not isinstance(roles, list)
            or not isinstance(source_evidence_ids, list)
            or not source_evidence_ids
        ):
            continue
        evidence_ids = {str(evidence_id) for evidence_id in source_evidence_ids}
        for role in roles:
            if role in matrix:
                evidence_by_role.setdefault(role, set()).update(evidence_ids)

    return [
        {
            "role": role,
            "required": bool(rule.get("required", True)),
            "present": bool(evidence_by_role.get(role)),
            "evidence_ids": sorted(evidence_by_role.get(role, ())),
            "description": str(rule.get("description", "")),
        }
        for role, rule in matrix.items()
    ]


def _has_text(value: object) -> bool:
    """True when a target field carries non-whitespace text."""
    if type(value) is str:
        return bool(value) and not value.isspace()
    text = value if isinstance(value, str) else str(value)
    return bool(text.strip())


def _report_run_kind_values(runs: list[dict[str, object]]) -> set[str]:
    """Return every ``run_kind`` in the report, normalized to text."""
    return {str(run.get("run_kind", "")) for run in runs}


def _report_matrix_roles(
    report: dict[str, object],
    matrix: dict[str, dict[str, object]],
) -> list[str]:
    # Each input is derived once for the whole matrix rather than per rule, so
    # matching stays O(roles + rows) instead of O(roles x rows).
    run_kind_values = _report_run_kind_values(_dict_list(report.get("runs")))
    targets = _dict_list(report.get("targets"))
    metrics = _dict_list(report.get("metrics"))
    # Collecting probe phases walks every probe row on both sides of the report,
    # so skip it entirely when no rule in the matrix asks for one.
    needs_probe_phases = any(rule.get("probe_phases") for rule in matrix.values())
    probe_phases = _probe_phases(report) if needs_probe_phases else frozenset()
    return [
        role
        for role, rule in matrix.items()
        if _rule_matches_report(
            rule=rule,
            run_kind_values=run_kind_values,
            targets=targets,
            metrics=metrics,
            probe_phases=probe_phases,
        )
    ]


def _rule_matches_report(
    *,
    rule: dict[str, object],
    run_kind_values: AbstractSet[str],
    targets: list[dict[str, object]],
    metrics: list[dict[str, object]],
    probe_phases: AbstractSet[str],
) -> bool:
    """Return True when a report satisfies one release-evidence matrix rule.

    Rule clauses are evaluated in declaration order and the first satisfied
    clause wins. An empty ``metric_prefixes`` entry means "any metric at all",
    and is decisive: it short-circuits the remaining clauses.
    """
    rule_get = rule.get
    run_kinds = rule_get("run_kinds", ())
    if run_kinds and not _string_frozenset(run_kinds).isdisjoint(run_kind_values):
        return True

    metric_prefixes = rule_get("metric_prefixes", ())
    if metric_prefixes:
        matches_any_metric, prefixes_by_initial = _metric_prefix_index(
            _string_tuple(metric_prefixes)
        )
        if matches_any_metric:
            return bool(metrics)
        for metric in metrics:
            metric_value = str(metric.get("metric", ""))
            if not metric_value:
                continue
            candidates = prefixes_by_initial.get(metric_value[0])
            if candidates is not None and metric_value.startswith(candidates):
                return True

    target_fields = rule_get("target_fields", ())
    if target_fields:
        target_field_set = _string_frozenset(target_fields)
        for target in targets:
            if target_field_set.isdisjoint(target):
                continue
            for field, value in target.items():
                if field in target_field_set and _has_text(value):
                    return True

    required_probe_phases = rule_get("probe_phases", ())
    if not required_probe_phases:
        return False
    return _string_frozenset(required_probe_phases).issubset(probe_phases)


@lru_cache(maxsize=128)
def _string_frozenset_from_tuple(values: tuple[object, ...]) -> frozenset[str]:
    return frozenset(str(item) for item in values)


@lru_cache(maxsize=128)
def _string_tuple_from_tuple(values: tuple[object, ...]) -> tuple[str, ...]:
    return tuple(str(item) for item in values)


@lru_cache(maxsize=128)
def _metric_prefix_index(
    prefixes: tuple[str, ...],
) -> tuple[bool, dict[str, tuple[str, ...]]]:
    """Group metric prefixes by first character.

    A rule may list many prefixes while most metrics share none of their initial
    characters, so bucketing lets those metrics be rejected with one lookup
    instead of one comparison per prefix. An empty prefix matches every metric
    and is reported separately.
    """
    by_initial: dict[str, list[str]] = {}
    for prefix in prefixes:
        if prefix:
            by_initial.setdefault(prefix[0], []).append(prefix)
    return "" in prefixes, {
        initial: tuple(grouped) for initial, grouped in by_initial.items()
    }


def _string_frozenset(values: object) -> frozenset[str]:
    if isinstance(values, tuple):
        return _string_frozenset_from_tuple(values)
    return frozenset(str(item) for item in values)  # type: ignore[union-attr]


def _string_tuple(values: object) -> tuple[str, ...]:
    if isinstance(values, tuple):
        return _string_tuple_from_tuple(values)
    return tuple(str(item) for item in values)  # type: ignore[union-attr]


def _telemetry_failures(report: dict[str, object]) -> list[str]:
    telemetry_summary = report.get("telemetry_summary")
    if not isinstance(telemetry_summary, dict):
        return ["telemetry_summary_missing"]
    failures: list[str] = []
    for side in ("baseline", "candidate"):
        side_rows = telemetry_summary.get(side)
        if not isinstance(side_rows, list) or not side_rows:
            failures.append(f"{side}:telemetry_summary_missing")
            continue
        for row in _dict_list(side_rows):
            telemetry_failures = row.get("telemetry_failures")
            if isinstance(telemetry_failures, list):
                failures.extend(
                    f"{side}:{row.get('run_id', '')}:{failure}"
                    for failure in telemetry_failures
                    if str(failure).strip()
                )
    return failures


def _probe_phase_duration_key(row: dict[str, object]) -> float:
    """Return the sort key for one probe phase, scoring unusable durations as 0.0.

    ``bool`` is excluded deliberately: it is a subclass of ``int``, so a JSON
    ``"duration_ms": true`` would otherwise score 1.0 and displace a real phase
    from the top five rather than ranking last with the other unusable values.
    """
    duration = row.get("duration_ms")
    if isinstance(duration, bool) or not isinstance(duration, (float, int, str)):
        return 0.0
    return float(duration or 0.0)


def _slowest_probe_phases(report: dict[str, object]) -> list[dict[str, object]]:
    """Return the five slowest probe phases, longest first, input order breaking ties."""
    probe_summary = report.get("probe_summary")
    if not isinstance(probe_summary, dict):
        return []
    def ranked_rows():
        order = 0
        for side in _PROBE_PHASE_SIDES:
            side_summary = probe_summary.get(side)
            if not isinstance(side_summary, dict):
                continue
            slowest_phases = side_summary.get("slowest_phases")
            if not isinstance(slowest_phases, list):
                continue
            for row in slowest_phases:
                if isinstance(row, dict):
                    # Negated order breaks duration ties toward the earlier row.
                    yield _probe_phase_duration_key(row), -order, side, row
                    order += 1

    top_rows = heapq.nlargest(5, ranked_rows())
    return [{"side": side, **row} for _duration_ms, _row_order, side, row in top_rows]


def _probe_phases(report: dict[str, object]) -> set[str]:
    phases: set[str] = set()
    probe_summary = report.get("probe_summary")
    if not isinstance(probe_summary, dict):
        return phases
    for side in _PROBE_PHASE_SIDES:
        side_summary = probe_summary.get(side)
        if not isinstance(side_summary, dict):
            continue
        for bucket in _PROBE_PHASE_BUCKETS:
            rows = side_summary.get(bucket)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                phase = str(row.get("phase", "")).strip()
                if phase:
                    phases.add(phase)
    return phases


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
