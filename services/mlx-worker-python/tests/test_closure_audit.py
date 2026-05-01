from __future__ import annotations

import builtins
import json
from pathlib import Path

import pytest

from worker.productization import closure_audit as closure_audit_module
from worker.productization.closure_audit import (
    build_closure_audit,
    render_closure_audit_json,
)


def test_build_closure_audit_classifies_accepted_risk_and_deferred_work(
    tmp_path: Path,
) -> None:
    repo_root = _seed_repo(tmp_path)

    report = build_closure_audit(repo_root, created_at_unix_ms=1_712_345_678_000)
    payload = report.to_dict()

    assert payload["schema_version"] == "melix.closure_audit.v1"
    assert payload["created_at_unix_ms"] == 1_712_345_678_000
    assert payload["metrics"]["closure_audit.blocker_count"] == 0
    assert payload["metrics"]["closure_audit.accepted_risk_count"] == 1
    assert payload["metrics"]["closure_audit.evidence_gap_count"] == 0
    assert payload["metrics"]["closure_audit.deferred_work_count"] == 1
    severities = {finding["severity"] for finding in payload["findings"]}
    assert severities == {"accepted_risk", "deferred_work"}
    assert payload["summary"]["top_unresolved_findings"] == [
        "M9.8 release-gate wiring remains deferred until ecosystem evidence is consumed by the release gate."
    ]

    emitted = render_closure_audit_json(report)
    assert emitted == render_closure_audit_json(report)
    assert json.loads(emitted) == payload


def test_build_closure_audit_reports_evidence_gap_for_missing_runbook_and_probe(
    tmp_path: Path,
) -> None:
    repo_root = _seed_repo(tmp_path)
    (repo_root / "docs/runbooks/connection-lifecycle.md").unlink()
    (repo_root / "scripts/m9_connection_smoke.py").write_text(
        "print('missing probe coverage')\n",
        encoding="utf-8",
    )

    report = build_closure_audit(repo_root, created_at_unix_ms=7)
    payload = report.to_dict()

    assert payload["metrics"]["closure_audit.evidence_gap_count"] == 2
    categories = [finding["category"] for finding in payload["findings"]]
    assert "runbook" in categories
    assert "probe_coverage" in categories
    assert payload["summary"]["top_unresolved_findings"] == [
        "Missing required M9 runbooks: docs/runbooks/connection-lifecycle.md",
        "Missing required M9 metric probes: disconnect.keepalive_gap_ms, disconnect.recovery_latency_ms, disconnect.resume_success_rate, disconnect.terminal_failure_count",
        "M9.8 release-gate wiring remains deferred until ecosystem evidence is consumed by the release gate.",
    ]


def test_build_closure_audit_reports_blocker_when_completed_surface_regresses(
    tmp_path: Path,
) -> None:
    repo_root = _seed_repo(
        tmp_path,
        execution_index_statuses={
            "M9.3": "completed",
            "M9.4": "completed",
            "M9.5": "pending",
            "M9.6": "completed",
            "M9.7": "pending",
            "M9.8": "pending",
        },
    )

    report = build_closure_audit(repo_root, created_at_unix_ms=9)
    payload = report.to_dict()

    assert payload["metrics"]["closure_audit.blocker_count"] == 1
    blocker = next(
        finding for finding in payload["findings"] if finding["severity"] == "blocker"
    )
    assert blocker["category"] == "milestone_status"
    assert blocker["finding_id"] == "m9-completed-surface-incomplete"
    assert blocker["required_follow_up"] == (
        "Complete M9.3 through M9.6 before treating the ecosystem closure surface as release-ready."
    )


def test_build_closure_audit_reports_release_gate_asset_and_policy_gaps(
    tmp_path: Path,
) -> None:
    repo_root = _seed_repo(tmp_path)
    (repo_root / "scripts/phase8_metrics_report.py").unlink()
    (repo_root / "infra/release/phase8-release-gate-policy.json").unlink()

    report = build_closure_audit(repo_root, created_at_unix_ms=11)
    payload = report.to_dict()

    assert payload["metrics"]["closure_audit.blocker_count"] == 1
    assert payload["metrics"]["closure_audit.evidence_gap_count"] == 1
    summaries = [finding["summary"] for finding in payload["findings"]]
    assert (
        "Missing required release-gate assets: "
        "infra/release/phase8-release-gate-policy.json, scripts/phase8_metrics_report.py"
    ) in summaries
    assert (
        "Phase 8 release-gate policy is missing required sections: "
        "install, benchmarks, training, recovery, audio, runtime_core, evaluation, quantization"
    ) in summaries


def test_collect_probe_sources_stops_reading_after_all_probe_slots_are_filled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = _seed_repo(tmp_path)
    docs_root = repo_root / "docs"
    probe_names = [
        probe_name
        for probe_group in closure_audit_module._REQUIRED_PROBES.values()
        for probe_name in probe_group
    ]
    repeated_probe_text = "\n".join(probe_names) + "\n"
    for index in range(3):
        (docs_root / f"a-probe-{index}.md").write_text(repeated_probe_text, encoding="utf-8")
    sentinel = docs_root / "z-after-saturation.md"
    sentinel.write_text("this file should not be read\n", encoding="utf-8")

    original_read_text = Path.read_text

    def tracked_read_text(self: Path, *args, **kwargs) -> str:
        if self == sentinel:
            raise AssertionError("probe scan should stop before reading files after saturation")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", tracked_read_text)

    probe_sources = closure_audit_module._collect_probe_sources(repo_root)

    for probe_name in probe_names:
        assert probe_sources[probe_name] == [
            "docs/a-probe-0.md",
            "docs/a-probe-1.md",
            "docs/a-probe-2.md",
        ]


def test_collect_probe_sources_uses_iterator_order_without_resorting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(closure_audit_module, "_iter_probe_text_files", lambda root: [])

    def fail_sorted(*args, **kwargs):
        raise AssertionError("_collect_probe_sources should not sort an already-sorted iterator")

    with pytest.raises(AssertionError, match="already-sorted iterator"):
        fail_sorted()

    monkeypatch.setattr(builtins, "sorted", fail_sorted)

    probe_sources = closure_audit_module._collect_probe_sources(tmp_path)

    assert probe_sources == {
        probe_name: []
        for probe_group in closure_audit_module._REQUIRED_PROBES.values()
        for probe_name in probe_group
    }


def test_load_milestone_statuses_streams_execution_index_without_read_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    execution_index = tmp_path / "execution-index.md"
    execution_index.write_text(
        "\n".join(
            [
                "# Execution Index",
                "",
                "- `M9.3` `docs/plans/m9.3.md`",
                "  Status: completed. done.",
                "- `M9.4` `docs/plans/m9.4.md`",
                "  Status: pending. todo.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    original_read_text = Path.read_text

    def fail_read_text(self: Path, *args, **kwargs) -> str:
        if self == execution_index:
            raise AssertionError("execution index parsing should not use Path.read_text")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    assert closure_audit_module._load_milestone_statuses(execution_index) == {
        "M9.3": "completed",
        "M9.4": "pending",
    }


def test_closure_audit_helper_fallbacks_cover_policy_and_probe_edge_cases(tmp_path: Path) -> None:
    missing_index = tmp_path / "missing-execution-index.md"
    assert closure_audit_module._load_milestone_statuses(missing_index) == {}

    invalid_policy = tmp_path / "invalid-policy.json"
    invalid_policy.write_text("{not-json}\n", encoding="utf-8")
    assert closure_audit_module._missing_release_gate_policy_sections(invalid_policy) == list(
        closure_audit_module._REQUIRED_RELEASE_GATE_POLICY_SECTIONS
    )

    list_policy = tmp_path / "list-policy.json"
    list_policy.write_text("[]\n", encoding="utf-8")
    assert closure_audit_module._missing_release_gate_policy_sections(list_policy) == list(
        closure_audit_module._REQUIRED_RELEASE_GATE_POLICY_SECTIONS
    )

    helper_root = tmp_path / "helper-root"
    helper_root.mkdir(parents=True, exist_ok=True)
    (helper_root / "docs").write_text("not a supported text root file\n", encoding="utf-8")
    services_dir = helper_root / "services"
    services_dir.mkdir()
    (services_dir / "ignored.bin").write_bytes(b"ignored")
    expected_text_file = services_dir / "kept.md"
    expected_text_file.write_text("kept\n", encoding="utf-8")
    assert closure_audit_module._iter_probe_text_files(helper_root) == [expected_text_file]

    first_probe_name = next(iter(closure_audit_module._REQUIRED_PROBES.values()))[0]
    partial_sources = {probe_name: [] for probe_group in closure_audit_module._REQUIRED_PROBES.values() for probe_name in probe_group}
    partial_sources[first_probe_name] = ["one", "two", "three"]
    assert closure_audit_module._probe_sources_complete(partial_sources) is False

    repo_root = tmp_path / "continue-root"
    (repo_root / "docs").mkdir(parents=True, exist_ok=True)
    all_probe_names = [
        probe_name
        for probe_group in closure_audit_module._REQUIRED_PROBES.values()
        for probe_name in probe_group
    ]
    target_probe = all_probe_names[0]
    for index in range(3):
        (repo_root / "docs" / f"a-target-{index}.md").write_text(f"{target_probe}\n", encoding="utf-8")
    (repo_root / "docs" / "b-fill-rest.md").write_text("\n".join(all_probe_names) + "\n", encoding="utf-8")

    continued_probe_sources = closure_audit_module._collect_probe_sources(repo_root)

    assert continued_probe_sources[target_probe] == [
        "docs/a-target-0.md",
        "docs/a-target-1.md",
        "docs/a-target-2.md",
    ]
    assert closure_audit_module._probe_sources_complete(continued_probe_sources) is False


def _seed_repo(
    root: Path,
    *,
    execution_index_statuses: dict[str, str] | None = None,
) -> Path:
    statuses = execution_index_statuses or {
        "M9.3": "completed",
        "M9.4": "completed",
        "M9.5": "completed",
        "M9.6": "completed",
        "M9.7": "pending",
        "M9.8": "pending",
    }
    repo_root = root / "repo"
    _write(
        repo_root / "docs/plans/2026-03-30-full-capability-roadmap-execution-index.md",
        "\n".join(
            [
                "# Melix Full Capability Roadmap Execution Index",
                "",
                *[
                    f"- `{milestone}` `docs/plans/{milestone.lower()}-placeholder.md`\n  Status: {status}. placeholder."
                    for milestone, status in statuses.items()
                ],
                "",
            ]
        ),
    )
    _write(
        repo_root / "docs/plans/2026-03-30-m9-7-security-and-stability-closure-audit.md",
        "# M9.7 Security And Stability Closure Audit Implementation Plan\n\n"
        "- repository-owned evidence only\n",
    )
    _write(
        repo_root / "infra/release/phase8-release-gate-policy.json",
        json.dumps(
            {
                "install": {},
                "benchmarks": {},
                "training": {},
                "recovery": {},
                "audio": {},
                "runtime_core": {},
                "evaluation": {},
                "quantization": {},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    _write(
        repo_root / "scripts/phase8_metrics_report.py",
        "print('phase8 metrics report')\n",
    )
    _write(
        repo_root / "docs/runbooks/phase-8-release-gates.md",
        "# Phase 8 Release Gates\n",
    )
    for relative_path in (
        "docs/runbooks/shared-access.md",
        "docs/runbooks/persistent-sessions.md",
        "docs/runbooks/rich-output-sanitization.md",
        "docs/runbooks/connection-lifecycle.md",
    ):
        _write(repo_root / relative_path, f"# {relative_path}\n")
    _write(
        repo_root / "scripts/m9_shared_access_smoke.py",
        "\n".join(
            [
                "metrics = {",
                '  "gateway.accepted_api_key_count": 2,',
                '  "shared_access.accepted_client_count": 3,',
                '  "shared_access.rejected_request_count": 1,',
                "}",
                "",
            ]
        ),
    )
    _write(
        repo_root / "scripts/m9_persistent_session_smoke.py",
        "\n".join(
            [
                "metrics = {",
                '  "persistent_session.restore_success_rate": 100,',
                '  "persistent_session.sign_out_latency_ms": 14.2,',
                "}",
                "",
            ]
        ),
    )
    _write(
        repo_root / "scripts/m9_sanitization_smoke.py",
        "\n".join(
            [
                "metrics = {",
                '  "sanitized_output.enforcement_count": 2,',
                '  "sanitized_output.blocked_html_fragment_count": 2,',
                '  "sanitized_output.unsafe_uri_rejection_count": 1,',
                "}",
                "",
            ]
        ),
    )
    _write(
        repo_root / "scripts/m9_connection_smoke.py",
        "\n".join(
            [
                "metrics = {",
                '  "disconnect.keepalive_gap_ms": 8.1,',
                '  "disconnect.recovery_latency_ms": 12.4,',
                '  "disconnect.resume_success_rate": 100,',
                '  "disconnect.terminal_failure_count": 1,',
                "}",
                "",
            ]
        ),
    )
    return repo_root


def _write(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
