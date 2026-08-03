from __future__ import annotations

import json

from scripts.agentic_tool_guardrail_diagnostics import (
    DIAGNOSTIC_BUNDLE_SCHEMA_VERSION,
    build_diagnostic_bundle,
    main,
)


def test_bundle_records_success_and_terminal_failure_without_sensitive_values() -> None:
    bundle = build_diagnostic_bundle()
    runs = bundle["runs"]

    assert bundle["schema_version"] == DIAGNOSTIC_BUNDLE_SCHEMA_VERSION
    assert isinstance(runs, list)
    assert [run["outcome"] for run in runs] == ["completed", "failed"]
    assert runs[0]["diagnostics"]["tool_execution_count"] == 2
    assert runs[0]["diagnostics"]["last_nudge_type"] == "required_steps_completed"
    assert runs[0]["diagnostics"]["thread_scope_id"] == "diagnostic-success"
    assert runs[0]["diagnostics"]["current_turn_tool_start"] == 0
    assert runs[0]["diagnostics"]["tool_result_export_policy"] == (
        "model_text_summary_ui_full"
    )
    assert all(
        event["thread_scope_id"] == "diagnostic-success"
        for event in runs[0]["events"]
    )
    assert runs[1]["diagnostics"]["final_failure_reason"] == (
        "malformed_response_budget_exhausted"
    )
    assert runs[1]["diagnostics"]["consecutive_malformed_responses"] == 2
    lifecycle_outcomes = [
        event["outcome"]
        for event in runs[0]["events"]
        if event["event_type"] == "tool_lifecycle"
    ]
    assert lifecycle_outcomes == [
        "authorized",
        "executing",
        "completed",
        "authorized",
        "executing",
        "completed",
        "retired",
        "retired",
    ]
    serialized = json.dumps(bundle, sort_keys=True)
    assert "SENSITIVE_MATCHING_QUERY" not in serialized
    assert "SENSITIVE_REJECTED_QUERY" not in serialized
    assert '"arguments"' not in serialized
    assert '"observation"' not in serialized

    parking = bundle["parking"]
    assert parking["approval_wait_count"] == 100
    assert parking["executor_capacity_available_min"] == 2
    assert parking["diagnostics"]["executor_leases_used"] == 0
    assert parking["diagnostics"]["parking_permits_used"] == 0
    assert parking["diagnostics"]["release_suppression_count"] == 1
    assert parking["diagnostics"]["release_reason_counts"] == {
        "cancelled": 33,
        "completed": 0,
        "runtime_reload": 34,
        "timed_out": 33,
    }
    assert parking["events"][-1]["event_type"] == "release_suppressed"


def test_cli_writes_operator_readable_bundle(tmp_path, capsys) -> None:
    output = tmp_path / "guardrail.json"

    exit_code = main(["--output", str(output)])

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == str(output)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == DIAGNOSTIC_BUNDLE_SCHEMA_VERSION
    assert payload["runs"][1]["diagnostics"]["terminal_failure_count"] == 1
    assert payload["parking"]["executor_capacity_available_min"] == 2
