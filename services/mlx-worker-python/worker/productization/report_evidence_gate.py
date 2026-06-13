from __future__ import annotations

import heapq
import json
from functools import lru_cache
from pathlib import Path
from typing import AbstractSet, Any

from worker.productization.benchmark_evaluation_report import validate_report_payload

REPORT_EVIDENCE_GATE_SCHEMA_VERSION = "melix.report_evidence_gate.v1"
_EMPTY_PROBE_PHASES: frozenset[str] = frozenset()

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
    report_path = Path(path)
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
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
    return {
        "path": str(path),
        "report_id": report.get("report_id", ""),
        "report_kind": report.get("report_kind", ""),
        "source_evidence_ids": list(report.get("source_evidence_ids", []))
        if isinstance(report.get("source_evidence_ids"), list)
        else [],
        "markdown_report_path": artifacts.get("markdown_report_path", ""),
        "validation_errors": validation_errors,
        "gate_result": gate_result.get("overall_result", "fail"),
        "blocking_failures": blocking_failures,
        "informational_results": _dict_list(gate_result.get("informational_results")),
        "known_gaps": list(report.get("known_gaps", []))
        if isinstance(report.get("known_gaps"), list)
        else [],
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
    matrix_roles = set(matrix)
    to_string = str
    for report in reports:
        roles = report.get("release_matrix_roles")
        source_evidence_ids = report.get("source_evidence_ids", [])
        if (
            not isinstance(roles, list)
            or not isinstance(source_evidence_ids, list)
            or not source_evidence_ids
        ):
            continue
        if len(roles) == 1:
            role = roles[0]
            if role in matrix_roles:
                evidence_ids_for_role = evidence_by_role.setdefault(role, set())
                for evidence_id in source_evidence_ids:
                    evidence_ids_for_role.add(to_string(evidence_id))
            continue
        evidence_ids = tuple(to_string(item) for item in source_evidence_ids)
        for role in roles:
            if role not in matrix_roles:
                continue
            evidence_by_role.setdefault(role, set()).update(evidence_ids)

    rows: list[dict[str, object]] = []
    for role, rule in matrix.items():
        evidence_ids = evidence_by_role.get(role, set())
        rows.append(
            {
                "role": role,
                "required": bool(rule.get("required", True)),
                "present": bool(evidence_ids),
                "evidence_ids": sorted(evidence_ids),
                "description": str(rule.get("description", "")),
            }
        )
    return rows


def _report_matrix_roles(
    report: dict[str, object],
    matrix: dict[str, dict[str, object]],
) -> list[str]:
    roles: list[str] = []
    runs = _dict_list(report.get("runs"))
    targets = _dict_list(report.get("targets"))
    metrics = _dict_list(report.get("metrics"))
    run_kind_values: frozenset[str] | None = None
    probe_phases: set[str] | None = None
    for role, rule in matrix.items():
        if _run_kind_only_rule(rule):
            if run_kind_values is None:
                run_kind_values = _report_run_kind_values(runs)
            if not _string_frozenset(rule.get("run_kinds", ())).isdisjoint(run_kind_values):
                roles.append(role)
            continue
        if rule.get("probe_phases") and probe_phases is None:
            probe_phases = _probe_phases(report)
        if _rule_matches_report(
            rule=rule,
            runs=runs,
            targets=targets,
            metrics=metrics,
            probe_phases=probe_phases if probe_phases is not None else _EMPTY_PROBE_PHASES,
        ):
            roles.append(role)
    return roles


def _run_kind_only_rule(rule: dict[str, object]) -> bool:
    return bool(rule.get("run_kinds")) and not (
        rule.get("metric_prefixes")
        or rule.get("target_fields")
        or rule.get("probe_phases")
    )


def _report_run_kind_values(runs: list[dict[str, object]]) -> frozenset[str]:
    run_kind_key = "run_kind"
    values: set[str] = set()
    values_add = values.add
    to_string = str
    for run in runs:
        run_kind = run.get(run_kind_key, "")
        if type(run_kind) is str:
            values_add(run_kind)
        else:
            values_add(to_string(run_kind))
    return frozenset(values)


def _rule_matches_report(
    *,
    rule: dict[str, object],
    runs: list[dict[str, object]],
    targets: list[dict[str, object]],
    metrics: list[dict[str, object]],
    probe_phases: AbstractSet[str],
) -> bool:
    run_kinds = rule.get("run_kinds", ())
    if run_kinds:
        run_kind_set = _string_frozenset(run_kinds)
        run_kind_key = "run_kind"
        for run in runs:
            run_kind = run.get(run_kind_key, "")
            if run_kind in run_kind_set:
                return True
        for run in runs:
            run_kind = run.get(run_kind_key, "")
            if type(run_kind) is not str and str(run_kind) in run_kind_set:
                return True
    metric_prefixes = rule.get("metric_prefixes", ())
    if metric_prefixes:
        (
            metric_prefix_tuple,
            metric_prefix_initials,
            metric_prefix_matches_empty,
        ) = _string_prefix_tuple(metric_prefixes)
        metric_key = "metric"
        to_string = str
        for metric in metrics:
            metric_value = to_string(metric.get(metric_key, ""))
            if metric_prefix_matches_empty or (
                metric_value
                and metric_value[0] in metric_prefix_initials
                and metric_value.startswith(metric_prefix_tuple)
            ):
                return True
    target_fields = rule.get("target_fields", ())
    if target_fields:
        target_field_set = _string_frozenset(target_fields)
        target_fields_are_disjoint = target_field_set.isdisjoint
        for target in targets:
            if target_fields_are_disjoint(target):
                continue
            for field, value in target.items():
                if field not in target_field_set:
                    continue
                if isinstance(value, str):
                    if value.strip():
                        return True
                elif str(value).strip():
                    return True
    required_probe_phases = rule.get("probe_phases", ())
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
def _string_prefix_tuple_from_tuple(
    values: tuple[object, ...],
) -> tuple[tuple[str, ...], frozenset[str], bool]:
    prefixes = tuple(str(item) for item in values)
    return prefixes, frozenset(prefix[0] for prefix in prefixes if prefix), "" in prefixes


def _string_frozenset(values: object) -> frozenset[str]:
    if isinstance(values, tuple):
        return _string_frozenset_from_tuple(values)
    return frozenset(str(item) for item in values)  # type: ignore[union-attr]


def _string_tuple(values: object) -> tuple[str, ...]:
    if isinstance(values, tuple):
        return _string_tuple_from_tuple(values)
    return tuple(str(item) for item in values)  # type: ignore[union-attr]


def _string_prefix_tuple(
    values: object,
) -> tuple[tuple[str, ...], frozenset[str], bool]:
    if isinstance(values, tuple):
        return _string_prefix_tuple_from_tuple(values)
    prefixes = tuple(str(item) for item in values)  # type: ignore[union-attr]
    return prefixes, frozenset(prefix[0] for prefix in prefixes if prefix), "" in prefixes


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
    duration = row.get("duration_ms")
    if isinstance(duration, (float, int, str)):
        return float(duration or 0.0)
    return 0.0


def _slowest_probe_phases(report: dict[str, object]) -> list[dict[str, object]]:
    probe_summary = report.get("probe_summary")
    if not isinstance(probe_summary, dict):
        return []
    rows: list[tuple[float, int, str, dict[str, object]]] = []
    row_index = 0
    rows_append = rows.append
    for side in ("baseline", "candidate"):
        side_summary = probe_summary.get(side)
        if not isinstance(side_summary, dict):
            continue
        slowest_phases = side_summary.get("slowest_phases")
        if not isinstance(slowest_phases, list):
            continue
        for row in slowest_phases:
            if not isinstance(row, dict):
                continue
            duration = row.get("duration_ms")
            if type(duration) is float:
                duration_ms = duration
            elif type(duration) is int:
                duration_ms = float(duration)
            elif type(duration) is str:
                duration_ms = float(duration or 0.0)
            else:
                duration_ms = 0.0
            rows_append((duration_ms, -row_index, side, row))
            row_index += 1
    return [
        {"side": side, **row}
        for _duration_ms, _row_order, side, row in heapq.nlargest(5, rows)
    ]


def _probe_phases(report: dict[str, object]) -> set[str]:
    phases: set[str] = set()
    probe_summary = report.get("probe_summary")
    if not isinstance(probe_summary, dict):
        return phases
    for side in ("baseline", "candidate"):
        side_summary = probe_summary.get(side)
        if not isinstance(side_summary, dict):
            continue
        for bucket in ("slowest_phases", "failed_phases", "skipped_phases", "fallback_phases"):
            for row in _dict_list(side_summary.get(bucket)):
                phase = str(row.get("phase", "")).strip()
                if phase:
                    phases.add(phase)
    return phases


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
