from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from worker.productization.benchmark_evaluation_report import validate_report_payload

REPORT_EVIDENCE_GATE_SCHEMA_VERSION = "melix.report_evidence_gate.v1"

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
    rows: list[dict[str, object]] = []
    for role, rule in matrix.items():
        evidence_ids: list[str] = []
        for report in reports:
            roles = report.get("release_matrix_roles")
            if isinstance(roles, list) and role in roles:
                evidence_ids.extend(str(item) for item in report.get("source_evidence_ids", []))
        rows.append(
            {
                "role": role,
                "required": bool(rule.get("required", True)),
                "present": bool(evidence_ids),
                "evidence_ids": sorted(set(evidence_ids)),
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
    probe_phases = _probe_phases(report)
    for role, rule in matrix.items():
        if _rule_matches_report(
            rule=rule,
            runs=runs,
            targets=targets,
            metrics=metrics,
            probe_phases=probe_phases,
        ):
            roles.append(role)
    return roles


def _rule_matches_report(
    *,
    rule: dict[str, object],
    runs: list[dict[str, object]],
    targets: list[dict[str, object]],
    metrics: list[dict[str, object]],
    probe_phases: set[str],
) -> bool:
    run_kinds = rule.get("run_kinds", ())
    if run_kinds:
        run_kind_set = _string_frozenset(run_kinds)
        for run in runs:
            if str(run.get("run_kind", "")) in run_kind_set:
                return True
    metric_prefixes = _string_tuple(rule.get("metric_prefixes", ()))
    if metric_prefixes and any(
        str(metric.get("metric", "")).startswith(metric_prefixes) for metric in metrics
    ):
        return True
    target_fields = _string_tuple(rule.get("target_fields", ()))
    if target_fields and any(str(target.get(field, "")).strip() for target in targets for field in target_fields):
        return True
    required_probe_phases = set(str(item) for item in rule.get("probe_phases", ()))
    return bool(required_probe_phases and required_probe_phases.issubset(probe_phases))


@lru_cache(maxsize=128)
def _string_frozenset_from_tuple(values: tuple[object, ...]) -> frozenset[str]:
    return frozenset(str(item) for item in values)


def _string_frozenset(values: object) -> frozenset[str]:
    if isinstance(values, tuple):
        return _string_frozenset_from_tuple(values)
    return frozenset(str(item) for item in values)  # type: ignore[union-attr]


@lru_cache(maxsize=128)
def _string_tuple_from_tuple(values: tuple[object, ...]) -> tuple[str, ...]:
    return tuple(str(item) for item in values)


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


def _slowest_probe_phases(report: dict[str, object]) -> list[dict[str, object]]:
    probe_summary = report.get("probe_summary")
    if not isinstance(probe_summary, dict):
        return []
    rows: list[dict[str, object]] = []
    for side in ("baseline", "candidate"):
        side_summary = probe_summary.get(side)
        if not isinstance(side_summary, dict):
            continue
        for row in _dict_list(side_summary.get("slowest_phases")):
            rows.append({"side": side, **row})
    return sorted(rows, key=lambda row: float(row.get("duration_ms") or 0.0), reverse=True)[:5]


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
