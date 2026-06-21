from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

from worker.productization.agent_reliability import (
    DEFAULT_AGENT_RELIABILITY_FIXTURE_ROOT,
    AgentReliabilityRunConfig,
    expand_ablation_presets,
    load_agent_reliability_scenarios,
    persist_agent_reliability_run,
    run_agent_reliability_track,
)
import worker.productization.agent_reliability as agent_reliability_module


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "agent_reliability_eval.py"


def _scenario_by_id() -> dict[str, object]:
    return {
        scenario.scenario_id: scenario
        for scenario in load_agent_reliability_scenarios(DEFAULT_AGENT_RELIABILITY_FIXTURE_ROOT)
    }


def test_expand_ablation_presets_returns_issue_required_guardrail_switches() -> None:
    presets = expand_ablation_presets()

    assert set(presets) == {
        "baseline",
        "no_response_rescue",
        "no_retry_nudges",
        "no_step_enforcement",
        "no_tool_error_recovery",
        "no_context_compaction",
        "all_guardrails_disabled",
    }
    assert presets["baseline"].enabled_guardrails == {
        "response_rescue": True,
        "retry_nudges": True,
        "step_enforcement": True,
        "tool_error_recovery": True,
        "context_compaction": True,
    }
    assert presets["all_guardrails_disabled"].enabled_guardrails == {
        "response_rescue": False,
        "retry_nudges": False,
        "step_enforcement": False,
        "tool_error_recovery": False,
        "context_compaction": False,
    }

    for preset_id, guardrail_name in {
        "no_response_rescue": "response_rescue",
        "no_retry_nudges": "retry_nudges",
        "no_step_enforcement": "step_enforcement",
        "no_tool_error_recovery": "tool_error_recovery",
        "no_context_compaction": "context_compaction",
    }.items():
        disabled = [
            name
            for name, enabled in presets[preset_id].enabled_guardrails.items()
            if not enabled
        ]
        assert disabled == [guardrail_name]


def test_load_agent_reliability_scenarios_preserves_tags_and_stateful_validator() -> None:
    scenarios = load_agent_reliability_scenarios(DEFAULT_AGENT_RELIABILITY_FIXTURE_ROOT)

    assert {scenario.scenario_id for scenario in scenarios} == {
        "stateful-ticket-close-001",
        "tool-error-recovery-search-001",
        "compaction-pressure-summary-001",
    }
    assert any("stateful_behavior" in scenario.tags for scenario in scenarios)
    assert any("error_recovery" in scenario.tags for scenario in scenarios)
    assert any("compaction_pressure" in scenario.tags for scenario in scenarios)

    stateful = _scenario_by_id()["stateful-ticket-close-001"]
    assert stateful.expected_backend_state == {
        "tickets": {"T-100": {"status": "closed"}}
    }
    assert stateful.tool_backend["tools"][0]["name"] == "update_ticket"
    assert stateful.responses_by_ablation["baseline"].startswith("<tool_call>")
    assert "all_guardrails_disabled" in stateful.responses_by_ablation


def test_stateful_scenario_fails_when_tool_argument_does_not_update_backend_state(
    tmp_path: Path,
) -> None:
    scenario = _scenario_by_id()["stateful-ticket-close-001"]
    result = run_agent_reliability_track(
        AgentReliabilityRunConfig(
            output_dir=tmp_path,
            model_id="fixture-model",
            backend="fixture",
            profile="ci",
        ),
        scenarios=(scenario,),
        ablations=(expand_ablation_presets()["no_tool_error_recovery"],),
    )

    assert len(result.rows) == 1
    row = result.rows[0]
    assert row["accuracy"] == 0.0
    assert row["completeness"] == 0.0
    assert row["validation_error_count"] == 1.0
    assert row["backend_state_match"] is False
    assert row["backend_state_mismatches"] == [
        {
            "path": "tickets.T-100.status",
            "expected": "closed",
            "actual": "open",
        }
    ]
    assert row["tool_calls"][0]["name"] == "update_ticket"
    assert row["tool_calls"][0]["arguments"]["status"] == "open"


def test_run_agent_reliability_track_records_required_metrics_per_row(
    tmp_path: Path,
) -> None:
    scenarios_by_id = _scenario_by_id()
    result = run_agent_reliability_track(
        AgentReliabilityRunConfig(
            output_dir=tmp_path,
            model_id="fixture-model",
            backend="fixture",
            profile="ci",
        ),
        scenarios=(
            scenarios_by_id["stateful-ticket-close-001"],
            scenarios_by_id["tool-error-recovery-search-001"],
        ),
        ablations=(
            expand_ablation_presets()["baseline"],
            expand_ablation_presets()["no_tool_error_recovery"],
        ),
    )

    assert len(result.rows) == 4
    for row in result.rows:
        assert row["schema_version"] == "melix.agent_reliability_row.v1"
        assert row["model_id"] == "fixture-model"
        assert row["backend"] == "fixture"
        assert row["profile"] == "ci"
        assert row["ablation_id"] in {"baseline", "no_tool_error_recovery"}
        assert row["scenario_id"] in {
            "stateful-ticket-close-001",
            "tool-error-recovery-search-001",
        }
        for metric_name in (
            "accuracy",
            "completeness",
            "wasted_tool_call_count",
            "retry_count",
            "nudge_count",
            "validation_error_count",
            "compaction_event_count",
            "elapsed_ms",
            "token_estimate",
            "cost_estimate_usd",
        ):
            assert isinstance(row[metric_name], float)

    summary = result.summary
    assert summary["schema_version"] == "melix.agent_reliability_summary.v1"
    assert summary["aggregate"]["row_count"] == 4
    assert summary["by_ablation"]["baseline"]["completion_rate"] == 1.0
    assert summary["by_ablation"]["no_tool_error_recovery"]["completion_rate"] < 1.0


def test_agent_reliability_resume_skips_completed_jsonl_rows(tmp_path: Path) -> None:
    scenarios = load_agent_reliability_scenarios(DEFAULT_AGENT_RELIABILITY_FIXTURE_ROOT)
    ablations = (
        expand_ablation_presets()["baseline"],
        expand_ablation_presets()["no_tool_error_recovery"],
    )
    first = persist_agent_reliability_run(
        AgentReliabilityRunConfig(
            output_dir=tmp_path,
            model_id="fixture-model",
            backend="fixture",
            profile="ci",
        ),
        scenarios=scenarios[:1],
        ablations=ablations[:1],
    )
    preseeded = first.rows_path.read_text(encoding="utf-8")

    resumed = persist_agent_reliability_run(
        AgentReliabilityRunConfig(
            output_dir=tmp_path,
            model_id="fixture-model",
            backend="fixture",
            profile="ci",
            resume=True,
        ),
        scenarios=scenarios[:2],
        ablations=ablations,
    )

    rows = [
        json.loads(line)
        for line in resumed.rows_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    identities = [row["row_identity"] for row in rows]
    assert len(rows) == 4
    assert len(set(identities)) == 4
    assert resumed.rows_path.read_text(encoding="utf-8").startswith(preseeded)
    assert resumed.summary["aggregate"]["resumed_row_count"] == 1


def test_agent_reliability_summary_reports_per_ablation_deltas(tmp_path: Path) -> None:
    result = persist_agent_reliability_run(
        AgentReliabilityRunConfig(
            output_dir=tmp_path,
            model_id="fixture-model",
            backend="fixture",
            profile="ci",
        ),
        scenarios=load_agent_reliability_scenarios(DEFAULT_AGENT_RELIABILITY_FIXTURE_ROOT),
        ablations=(
            expand_ablation_presets()["baseline"],
            expand_ablation_presets()["no_tool_error_recovery"],
            expand_ablation_presets()["all_guardrails_disabled"],
        ),
    )

    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    report = result.report_path.read_text(encoding="utf-8")

    assert summary["by_ablation"]["baseline"]["completion_rate"] == 1.0
    assert summary["deltas_vs_baseline"]["no_tool_error_recovery"]["completion_rate_delta"] < 0.0
    assert "## Per-Ablation Deltas" in report
    assert "| no_tool_error_recovery |" in report
    assert "wasted_tool_call_delta" in report
    assert "stateful-ticket-close-001" in report


def test_agent_reliability_script_writes_fixture_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    spec = importlib.util.spec_from_file_location("agent_reliability_eval", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    output_dir = tmp_path / "script-output"
    exit_code = module.main(
        [
            "--fixture-root",
            str(DEFAULT_AGENT_RELIABILITY_FIXTURE_ROOT),
            "--output-dir",
            str(output_dir),
            "--model-id",
            "fixture-model",
            "--backend",
            "fixture",
            "--profile",
            "ci",
            "--ablation",
            "baseline",
            "--ablation",
            "no_tool_error_recovery",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary_path"] == str(output_dir / "agent-reliability-summary.json")
    assert (output_dir / "agent-reliability-rows.jsonl").is_file()
    assert (output_dir / "agent-reliability-summary.json").is_file()
    assert (output_dir / "agent-reliability-report.md").is_file()
    assert json.loads((output_dir / "agent-reliability-summary.json").read_text(encoding="utf-8"))[
        "aggregate"
    ]["row_count"] == 6


def test_agent_reliability_loader_and_script_cover_error_edges(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert agent_reliability_module._load_existing_rows(tmp_path / "missing.jsonl") == ()
    assert agent_reliability_module._dict_list("bad") == []
    assert agent_reliability_module._wasted_tool_call_count(
        [{"name": "unexpected", "arguments": {}}],
        _scenario_by_id()["compaction-pressure-summary-001"],
    ) == 0.0
    assert agent_reliability_module._state_mismatches(
        expected={"state": {"nested": "ok"}},
        actual={},
    ) == [{"path": "state", "expected": {"nested": "ok"}, "actual": None}]

    bad_manifest = tmp_path / "bad-manifest"
    bad_manifest.mkdir()
    (bad_manifest / "manifest.json").write_text('{"schema_version":"bad"}\n', encoding="utf-8")
    (bad_manifest / "scenarios.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported agent reliability fixture manifest"):
        load_agent_reliability_scenarios(bad_manifest)

    count_mismatch = tmp_path / "count-mismatch"
    count_mismatch.mkdir()
    (count_mismatch / "manifest.json").write_text(
        '{"schema_version":"melix.agent_reliability_fixture.v1","scenario_count":1}\n',
        encoding="utf-8",
    )
    (count_mismatch / "scenarios.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="scenario_count mismatch"):
        load_agent_reliability_scenarios(count_mismatch)

    invalid_json = tmp_path / "invalid-json"
    invalid_json.mkdir()
    (invalid_json / "manifest.json").write_text(
        '{"schema_version":"melix.agent_reliability_fixture.v1","scenario_count":1}\n',
        encoding="utf-8",
    )
    (invalid_json / "scenarios.jsonl").write_text("{bad\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON"):
        load_agent_reliability_scenarios(invalid_json)

    missing_id = tmp_path / "missing-id"
    missing_id.mkdir()
    (missing_id / "manifest.json").write_text(
        '{"schema_version":"melix.agent_reliability_fixture.v1","scenario_count":1}\n',
        encoding="utf-8",
    )
    (missing_id / "scenarios.jsonl").write_text(
        json.dumps({"title": "Missing id", "tags": ["plumbing"], "responses_by_ablation": {"baseline": "ok"}}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must include id"):
        load_agent_reliability_scenarios(missing_id)

    spec = importlib.util.spec_from_file_location("agent_reliability_eval_edges", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    with pytest.raises(ValueError, match="Unknown agent reliability ablation"):
        module.main(
            [
                "--fixture-root",
                str(DEFAULT_AGENT_RELIABILITY_FIXTURE_ROOT),
                "--output-dir",
                str(tmp_path / "bad-output"),
                "--ablation",
                "missing",
            ]
        )

    assert (
        module.main(
            [
                "--fixture-root",
                str(DEFAULT_AGENT_RELIABILITY_FIXTURE_ROOT),
                "--output-dir",
                str(tmp_path / "text-output"),
                "--ablation",
                "baseline",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "Agent reliability report:" in output
    assert "Rows:" in output
