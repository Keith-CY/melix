from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


_CLOSURE_AUDIT_SCHEMA_VERSION = "melix.closure_audit.v1"
_REQUIRED_RELEASE_GATE_FILES = (
    "infra/release/phase8-release-gate-policy.json",
    "docs/runbooks/phase-8-release-gates.md",
    "scripts/phase8_metrics_report.py",
)
_REQUIRED_RELEASE_GATE_POLICY_SECTIONS = (
    "install",
    "benchmarks",
    "training",
    "recovery",
    "audio",
    "runtime_core",
    "evaluation",
    "quantization",
)
_REQUIRED_RUNBOOKS = (
    "docs/runbooks/shared-access.md",
    "docs/runbooks/persistent-sessions.md",
    "docs/runbooks/rich-output-sanitization.md",
    "docs/runbooks/connection-lifecycle.md",
)
_REQUIRED_COMPLETED_MILESTONES = ("M9.3", "M9.4", "M9.5", "M9.6")
_M9_DEFERRED_MILESTONE = "M9.8"
_SCOPE_DECISION_SOURCE = "docs/plans/2026-03-30-m9-7-security-and-stability-closure-audit.md"
_EXECUTION_INDEX_PATH = "docs/plans/2026-03-30-full-capability-roadmap-execution-index.md"
_REQUIRED_PROBES: dict[str, tuple[str, ...]] = {
    "m9.3.shared_access": (
        "gateway.accepted_api_key_count",
        "shared_access.accepted_client_count",
        "shared_access.rejected_request_count",
    ),
    "m9.4.persistent_sessions": (
        "persistent_session.restore_success_rate",
        "persistent_session.sign_out_latency_ms",
    ),
    "m9.5.rich_output_sanitization": (
        "sanitized_output.enforcement_count",
        "sanitized_output.blocked_html_fragment_count",
        "sanitized_output.unsafe_uri_rejection_count",
    ),
    "m9.6.connection_lifecycle": (
        "disconnect.keepalive_gap_ms",
        "disconnect.recovery_latency_ms",
        "disconnect.resume_success_rate",
        "disconnect.terminal_failure_count",
    ),
}
_PREFERRED_PROBE_TEXT_FILES = (
    "docs/runbooks/security-and-stability-closure.md",
    "docs/runbooks/shared-access.md",
    "docs/runbooks/persistent-sessions.md",
    "docs/runbooks/rich-output-sanitization.md",
    "docs/runbooks/connection-lifecycle.md",
    "progress.md",
)
_TEXT_SEARCH_ROOTS = ("docs", "scripts", "services", "tests", "README.md", "progress.md", "task_plan.md")
_TEXT_FILE_SUFFIXES = (".md", ".py", ".swift", ".json", ".txt", ".yaml", ".yml")
_FINDING_SEVERITY_PRIORITY = {
    "blocker": 0,
    "evidence_gap": 1,
    "deferred_work": 2,
    "accepted_risk": 3,
}
_FINDING_CATEGORY_PRIORITY = {
    "milestone_status": 0,
    "release_gate_policy": 1,
    "release_gate_assets": 2,
    "runbook": 3,
    "probe_coverage": 4,
    "release_gate_followup": 5,
    "scope_constraint": 6,
}


@dataclass(frozen=True)
class ClosureAuditFinding:
    finding_id: str
    severity: str
    category: str
    summary: str
    evidence_sources: tuple[str, ...]
    probe_coverage: tuple[str, ...]
    required_follow_up: str = ""

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "finding_id": self.finding_id,
            "severity": self.severity,
            "category": self.category,
            "summary": self.summary,
            "evidence_sources": list(self.evidence_sources),
            "probe_coverage": list(self.probe_coverage),
        }
        if self.required_follow_up:
            payload["required_follow_up"] = self.required_follow_up
        return payload


@dataclass(frozen=True)
class ClosureAuditReport:
    schema_version: str
    created_at_unix_ms: int
    repo_root: str
    findings: tuple[ClosureAuditFinding, ...]
    metrics: dict[str, float]
    summary: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "created_at_unix_ms": self.created_at_unix_ms,
            "repo_root": self.repo_root,
            "findings": [finding.to_dict() for finding in self.findings],
            "metrics": dict(self.metrics),
            "summary": dict(self.summary),
        }


def build_closure_audit(
    repo_root: str | Path,
    *,
    created_at_unix_ms: int | None = None,
) -> ClosureAuditReport:
    root = Path(repo_root).resolve()
    findings: list[ClosureAuditFinding] = []

    execution_index = root / _EXECUTION_INDEX_PATH
    milestone_statuses = _load_milestone_statuses(execution_index)
    incomplete_completed_surface = [
        milestone
        for milestone in _REQUIRED_COMPLETED_MILESTONES
        if milestone_statuses.get(milestone) != "completed"
    ]
    if incomplete_completed_surface:
        findings.append(
            ClosureAuditFinding(
                finding_id="m9-completed-surface-incomplete",
                severity="blocker",
                category="milestone_status",
                summary=(
                    "Completed M9 ecosystem milestones remain unresolved: "
                    + ", ".join(incomplete_completed_surface)
                ),
                evidence_sources=(_EXECUTION_INDEX_PATH,),
                probe_coverage=(),
                required_follow_up=(
                    "Complete M9.3 through M9.6 before treating the ecosystem closure surface "
                    "as release-ready."
                ),
            )
        )

    missing_release_gate_files = _missing_paths(root, _REQUIRED_RELEASE_GATE_FILES)
    if missing_release_gate_files:
        findings.append(
            ClosureAuditFinding(
                finding_id="phase8-release-gate-evidence-missing",
                severity="evidence_gap",
                category="release_gate_assets",
                summary=(
                    "Missing required release-gate assets: "
                    + ", ".join(missing_release_gate_files)
                ),
                evidence_sources=tuple(missing_release_gate_files),
                probe_coverage=(),
                required_follow_up=(
                    "Restore the checked-in release-gate policy, runbook, and phase-metrics "
                    "entrypoint before re-running the closure audit."
                ),
            )
        )

    policy_path = root / "infra/release/phase8-release-gate-policy.json"
    missing_policy_sections = _missing_release_gate_policy_sections(policy_path)
    if missing_policy_sections:
        findings.append(
            ClosureAuditFinding(
                finding_id="phase8-release-gate-policy-incomplete",
                severity="blocker",
                category="release_gate_policy",
                summary=(
                    "Phase 8 release-gate policy is missing required sections: "
                    + ", ".join(missing_policy_sections)
                ),
                evidence_sources=("infra/release/phase8-release-gate-policy.json",),
                probe_coverage=(),
                required_follow_up=(
                    "Restore the missing policy sections before treating the closure audit as "
                    "release-ready evidence."
                ),
            )
        )

    missing_runbooks = _missing_paths(root, _REQUIRED_RUNBOOKS)
    if missing_runbooks:
        findings.append(
            ClosureAuditFinding(
                finding_id="m9-required-runbooks-missing",
                severity="evidence_gap",
                category="runbook",
                summary=(
                    "Missing required M9 runbooks: "
                    + ", ".join(missing_runbooks)
                ),
                evidence_sources=tuple(missing_runbooks),
                probe_coverage=(),
                required_follow_up=(
                    "Add the missing operator runbooks before treating M9 evidence as closed."
                ),
            )
        )

    probe_sources = _collect_probe_sources(root)
    missing_probes = [
        probe_name
        for probe_names in _REQUIRED_PROBES.values()
        for probe_name in probe_names
        if not probe_sources[probe_name]
    ]
    if missing_probes:
        findings.append(
            ClosureAuditFinding(
                finding_id="m9-metric-probe-coverage-missing",
                severity="evidence_gap",
                category="probe_coverage",
                summary=(
                    "Missing required M9 metric probes: "
                    + ", ".join(missing_probes)
                ),
                evidence_sources=_evidence_sources_for_probe_gap(root),
                probe_coverage=tuple(missing_probes),
                required_follow_up=(
                    "Restore the missing metric probe vocabulary in repository-owned smoke, "
                    "test, or runbook evidence."
                ),
            )
        )

    if milestone_statuses.get(_M9_DEFERRED_MILESTONE) != "completed":
        findings.append(
            ClosureAuditFinding(
                finding_id="m9-8-release-gate-follow-up",
                severity="deferred_work",
                category="release_gate_followup",
                summary=(
                    "M9.8 release-gate wiring remains deferred until ecosystem evidence is "
                    "consumed by the release gate."
                ),
                evidence_sources=(_EXECUTION_INDEX_PATH,),
                probe_coverage=(),
                required_follow_up=(
                    "Wire the closure audit and M9 smoke evidence into the release gate under "
                    "M9.8."
                ),
            )
        )

    findings.append(
        ClosureAuditFinding(
            finding_id="repository-owned-evidence-scope",
            severity="accepted_risk",
            category="scope_constraint",
            summary=(
                "The closure audit intentionally consumes repository-owned evidence and does "
                "not claim external scanner or adversarial-traffic coverage."
            ),
            evidence_sources=(_SCOPE_DECISION_SOURCE,),
            probe_coverage=(),
        )
    )

    ordered_findings = tuple(
        sorted(
            findings,
            key=lambda finding: (
                _FINDING_SEVERITY_PRIORITY[finding.severity],
                _FINDING_CATEGORY_PRIORITY.get(finding.category, 99),
                finding.finding_id,
            ),
        )
    )
    metrics = {
        "closure_audit.blocker_count": float(
            sum(1 for finding in ordered_findings if finding.severity == "blocker")
        ),
        "closure_audit.accepted_risk_count": float(
            sum(1 for finding in ordered_findings if finding.severity == "accepted_risk")
        ),
        "closure_audit.evidence_gap_count": float(
            sum(1 for finding in ordered_findings if finding.severity == "evidence_gap")
        ),
        "closure_audit.deferred_work_count": float(
            sum(1 for finding in ordered_findings if finding.severity == "deferred_work")
        ),
    }
    unresolved_findings = [
        finding.summary
        for finding in ordered_findings
        if finding.severity in {"blocker", "evidence_gap", "deferred_work"}
    ]
    summary = {
        "top_unresolved_findings": unresolved_findings[:3],
        "required_runbooks": list(_REQUIRED_RUNBOOKS),
        "required_probe_count": sum(len(probes) for probes in _REQUIRED_PROBES.values()),
        "covered_probe_count": sum(1 for matches in probe_sources.values() if matches),
    }

    return ClosureAuditReport(
        schema_version=_CLOSURE_AUDIT_SCHEMA_VERSION,
        created_at_unix_ms=(
            created_at_unix_ms if created_at_unix_ms is not None else int(time.time() * 1_000)
        ),
        repo_root=str(root),
        findings=ordered_findings,
        metrics=metrics,
        summary=summary,
    )


def render_closure_audit_json(report: ClosureAuditReport) -> str:
    return json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"


def _load_milestone_statuses(execution_index_path: Path) -> dict[str, str]:
    statuses: dict[str, str] = {}
    if not execution_index_path.exists():
        return statuses

    current_milestone = ""
    with execution_index_path.open(encoding="utf-8") as execution_index_file:
        for raw_line in execution_index_file:
            line = raw_line.strip()
            if line.startswith("- `M9."):
                current_milestone = line.split("`", 2)[1]
                continue
            if current_milestone and line.startswith("Status:"):
                status = line.split(":", 1)[1].strip().split(".", 1)[0].split()[0].lower()
                statuses[current_milestone] = status
                current_milestone = ""
    return statuses


def _missing_paths(root: Path, relative_paths: tuple[str, ...]) -> list[str]:
    return [relative_path for relative_path in relative_paths if not (root / relative_path).exists()]


def _missing_release_gate_policy_sections(policy_path: Path) -> list[str]:
    if not policy_path.exists():
        return list(_REQUIRED_RELEASE_GATE_POLICY_SECTIONS)
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return list(_REQUIRED_RELEASE_GATE_POLICY_SECTIONS)
    if not isinstance(payload, dict):
        return list(_REQUIRED_RELEASE_GATE_POLICY_SECTIONS)
    return [
        section
        for section in _REQUIRED_RELEASE_GATE_POLICY_SECTIONS
        if section not in payload
    ]


def _collect_probe_sources(root: Path) -> dict[str, list[str]]:
    probe_sources = {
        probe_name: []
        for probe_names in _REQUIRED_PROBES.values()
        for probe_name in probe_names
    }
    scanned_relative_paths: set[str] = set()
    for file_path in _iter_preferred_probe_text_files(root):
        _scan_probe_source_file(
            file_path=file_path,
            root=root,
            probe_sources=probe_sources,
            scanned_relative_paths=scanned_relative_paths,
        )
        if _probe_sources_complete(probe_sources):
            return probe_sources
    for file_path in _iter_probe_text_files(root):
        _scan_probe_source_file(
            file_path=file_path,
            root=root,
            probe_sources=probe_sources,
            scanned_relative_paths=scanned_relative_paths,
        )
        if _probe_sources_complete(probe_sources):
            break
    return probe_sources


def _scan_probe_source_file(
    *,
    file_path: Path,
    root: Path,
    probe_sources: dict[str, list[str]],
    scanned_relative_paths: set[str],
) -> None:
    relative_path = file_path.relative_to(root).as_posix()
    if relative_path in scanned_relative_paths:
        return
    scanned_relative_paths.add(relative_path)
    contents = file_path.read_text(encoding="utf-8", errors="ignore")
    for probe_name, matches in probe_sources.items():
        if len(matches) >= 3:
            continue
        if probe_name in contents:
            matches.append(relative_path)


def _probe_sources_complete(probe_sources: dict[str, list[str]]) -> bool:
    return all(len(matches) >= 3 for matches in probe_sources.values())


def _iter_preferred_probe_text_files(root: Path) -> Iterator[Path]:
    for relative_path in _PREFERRED_PROBE_TEXT_FILES:
        candidate = root / relative_path
        if candidate.is_file() and candidate.suffix in _TEXT_FILE_SUFFIXES:
            yield candidate


def _iter_probe_text_files(root: Path) -> Iterator[Path]:
    for entry in _TEXT_SEARCH_ROOTS:
        candidate = root / entry
        if candidate.is_file():
            if candidate.suffix in _TEXT_FILE_SUFFIXES:
                yield candidate
            continue
        if not candidate.exists():
            continue
        yield from _iter_text_files_sorted(candidate)


def _iter_text_files_sorted(root: Path) -> Iterator[Path]:
    with os.scandir(root) as scandir_entries:
        entries = sorted(scandir_entries, key=lambda entry: entry.name)
    for entry in entries:
        entry_path = Path(entry.path)
        if entry.is_dir(follow_symlinks=False):
            yield from _iter_text_files_sorted(entry_path)
            continue
        if entry.is_file(follow_symlinks=False) and entry.name.endswith(_TEXT_FILE_SUFFIXES):
            yield entry_path



def _evidence_sources_for_probe_gap(root: Path) -> tuple[str, ...]:
    sources = [
        relative_path
        for relative_path in (
            "scripts/m9_shared_access_smoke.py",
            "scripts/m9_persistent_session_smoke.py",
            "scripts/m9_sanitization_smoke.py",
            "scripts/m9_connection_smoke.py",
        )
        if (root / relative_path).exists()
    ]
    return tuple(sources)
