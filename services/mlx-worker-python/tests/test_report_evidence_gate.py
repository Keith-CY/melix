from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import report_evidence_gate as report_evidence_gate_script
import worker.productization.report_evidence_gate as report_evidence_gate_module
from worker.productization.benchmark_evaluation_report import (
    build_benchmark_evaluation_report,
    write_report_outputs,
)
from worker.productization.report_evidence_gate import (
    build_report_evidence_gate,
    load_report_payload,
    render_pr_evidence_markdown,
)


def _run_evidence(
    *,
    run_id: str,
    run_kind: str,
    decode_ms: float,
    telemetry_failures: list[str] | None = None,
    adapter_id: str = "adapter-a",
) -> dict[str, object]:
    failures = telemetry_failures or []
    probes = [
        {
            "run_id": run_id,
            "trace_id": f"{run_id}:trace",
            "span_id": f"{run_id}:{phase}",
            "parent_span_id": f"{run_id}:root",
            "component": component,
            "phase": phase,
            "started_at_monotonic_ms": index * 10,
            "duration_ms": duration_ms,
            "status": "completed",
            "error_stage": "",
            "error_code": "",
            "attributes": {},
        }
        for index, (component, phase, duration_ms) in enumerate(
            (
                ("runtime", "runtime_prepare", 1.0),
                ("runtime", "model_load", 2.0),
                ("runtime", "decode", decode_ms),
            ),
            start=1,
        )
    ]
    telemetry_summary: dict[str, object] = {
        "schema_version": "melix.telemetry_summary.v1",
        "collector_status": "partial" if failures else "collected",
        "time_series_path": "telemetry-samples.jsonl",
        "telemetry_failures": failures,
        "sample_count": 2,
    }
    if not failures:
        telemetry_summary.update(
            {
                "average_system_power_w": 15.0,
                "peak_system_power_w": 16.0,
                "watts_per_output_token": 1.5,
            }
        )
    return {
        "schema_version": "melix.run_evidence.v1",
        "run_id": run_id,
        "melix_commit": "abc123",
        "git_branch": "codex/pr-release-evidence-gate",
        "dirty_worktree": False,
        "run_kind": run_kind,
        "started_at": 1_779_000_000_000,
        "ended_at": 1_779_000_001_000,
        "duration_ms": 1000,
        "status": "completed",
        "command": "melix report evidence fixture",
        "artifact_root": f"/tmp/{run_id}",
        "target_model_id": "mlx-community/test-model",
        "hf_repo_id": "mlx-community/test-model",
        "task_kind": "text-generation",
        "model_snapshot": "model-sha",
        "adapter_id": adapter_id,
        "adapter_snapshot": "adapter-sha" if adapter_id else "",
        "runtime_kind": "mlx",
        "runtime_config": {"quantization": "4bit"},
        "dataset_ref": "fixture.dataset",
        "dataset_revision": "dataset-sha",
        "suite_id": "smoke",
        "sample_count": 1,
        "input_digest": "input-sha",
        "prompt_template_digest": "prompt-sha",
        "generation_config": {"max_tokens": 16},
        "metrics": [{"name": "decode_ms", "value": decode_ms, "unit": "ms"}],
        "probe_timeline": probes,
        "telemetry_summary": telemetry_summary,
        "artifacts": [{"kind": "probe_timeline", "path": "probes.jsonl", "role": "diagnostic"}],
        "failure_summary": {},
        "fallback_summary": {},
    }


def _write_report(
    tmp_path: Path,
    name: str,
    *,
    run_kind: str,
    baseline_decode_ms: float = 10.0,
    candidate_decode_ms: float = 10.0,
    telemetry_failures: list[str] | None = None,
    adapter_id: str = "adapter-a",
) -> Path:
    report = build_benchmark_evaluation_report(
        baseline={
            "run_evidence": [
                _run_evidence(
                    run_id=f"{name}-base",
                    run_kind=run_kind,
                    decode_ms=baseline_decode_ms,
                    adapter_id=adapter_id,
                )
            ]
        },
        candidate={
            "run_evidence": [
                _run_evidence(
                    run_id=f"{name}-head",
                    run_kind=run_kind,
                    decode_ms=candidate_decode_ms,
                    telemetry_failures=telemetry_failures,
                    adapter_id=adapter_id,
                )
            ]
        },
        report_kind="release_gate",
    )
    outputs = write_report_outputs(report=report, output_dir=tmp_path / name)
    return outputs["json"]


def test_report_evidence_gate_run_kind_rules_accept_non_tuple_iterables() -> None:
    assert report_evidence_gate_module._rule_matches_report(
        rule={"run_kinds": {"evaluation", "serving_benchmark"}},
        runs=[{"run_kind": "serving_benchmark"}],
        targets=[],
        metrics=[],
        probe_phases=set(),
    )
    assert not report_evidence_gate_module._rule_matches_report(
        rule={"run_kinds": {"evaluation"}},
        runs=[{"run_kind": "serving_benchmark"}],
        targets=[],
        metrics=[],
        probe_phases=set(),
    )


def test_report_evidence_gate_run_kind_tuple_rules_reuse_normalized_set() -> None:
    report_evidence_gate_module._string_frozenset_from_tuple.cache_clear()
    rule = {"run_kinds": ("evaluation", "serving_benchmark")}

    assert report_evidence_gate_module._rule_matches_report(
        rule=rule,
        runs=[{"run_kind": "serving_benchmark"}],
        targets=[],
        metrics=[],
        probe_phases=set(),
    )
    assert report_evidence_gate_module._rule_matches_report(
        rule=rule,
        runs=[{"run_kind": "evaluation"}],
        targets=[],
        metrics=[],
        probe_phases=set(),
    )

    cache_info = report_evidence_gate_module._string_frozenset_from_tuple.cache_info()
    assert cache_info.hits >= 1
    assert cache_info.misses == 1


def test_report_evidence_gate_run_kind_list_rules_reflect_mutation() -> None:
    run_kinds = ["evaluation"]
    rule = {"run_kinds": run_kinds}

    assert not report_evidence_gate_module._rule_matches_report(
        rule=rule,
        runs=[{"run_kind": "serving_benchmark"}],
        targets=[],
        metrics=[],
        probe_phases=set(),
    )
    run_kinds.append("serving_benchmark")
    assert report_evidence_gate_module._rule_matches_report(
        rule=rule,
        runs=[{"run_kind": "serving_benchmark"}],
        targets=[],
        metrics=[],
        probe_phases=set(),
    )


def test_report_evidence_gate_tuple_rule_fields_reuse_normalized_tuple() -> None:
    report_evidence_gate_module._string_tuple_from_tuple.cache_clear()
    rule = {"metric_prefixes": ("adapter.",), "target_fields": ("adapter_id",)}

    assert report_evidence_gate_module._rule_matches_report(
        rule=rule,
        runs=[],
        targets=[],
        metrics=[{"metric": "adapter.latency_ms"}],
        probe_phases=set(),
    )
    assert report_evidence_gate_module._rule_matches_report(
        rule=rule,
        runs=[],
        targets=[{"adapter_id": "adapter-a"}],
        metrics=[],
        probe_phases=set(),
    )

    cache_info = report_evidence_gate_module._string_tuple_from_tuple.cache_info()
    assert cache_info.hits >= 1
    assert cache_info.misses == 2


def test_report_evidence_gate_list_rule_fields_reflect_mutation() -> None:
    metric_prefixes = ["adapter."]
    target_fields = ["adapter_id"]
    rule = {"metric_prefixes": metric_prefixes, "target_fields": target_fields}

    assert not report_evidence_gate_module._rule_matches_report(
        rule=rule,
        runs=[],
        targets=[{"adapter_snapshot": "snapshot-a"}],
        metrics=[{"metric": "runtime.prepare_ms"}],
        probe_phases=set(),
    )
    metric_prefixes.append("runtime.")
    target_fields.append("adapter_snapshot")
    assert report_evidence_gate_module._rule_matches_report(
        rule=rule,
        runs=[],
        targets=[],
        metrics=[{"metric": "runtime.prepare_ms"}],
        probe_phases=set(),
    )
    assert report_evidence_gate_module._rule_matches_report(
        rule=rule,
        runs=[],
        targets=[{"adapter_snapshot": "snapshot-a"}],
        metrics=[],
        probe_phases=set(),
    )


def test_report_evidence_gate_passes_complete_release_matrix(tmp_path: Path) -> None:
    serving_report = _write_report(tmp_path, "serving", run_kind="serving_benchmark")
    evaluation_report = _write_report(tmp_path, "evaluation", run_kind="evaluation")

    gate = build_report_evidence_gate(
        [serving_report, evaluation_report],
        require_release_matrix=True,
    )

    assert gate["passed"] is True
    assert {row["role"]: row["present"] for row in gate["release_matrix"]} == {
        "serving_benchmark": True,
        "dialogue_event_evaluation": True,
        "adapter_check": True,
        "runtime_check": True,
    }
    markdown = render_pr_evidence_markdown(gate)
    assert "Report JSON" in markdown
    assert "serving-head" in markdown


def test_report_evidence_gate_reports_blocking_metrics_and_probe_phase(tmp_path: Path) -> None:
    report_path = _write_report(
        tmp_path,
        "regression",
        run_kind="serving_benchmark",
        baseline_decode_ms=10.0,
        candidate_decode_ms=20.0,
    )

    gate = build_report_evidence_gate([report_path])

    assert gate["passed"] is False
    assert gate["blocking_failures"][0]["source"] == "gate_metric"
    assert gate["blocking_failures"][0]["metric"] == (
        "probe.serving_benchmark.runtime.decode.duration_ms_mean"
    )
    assert gate["reports"][0]["slowest_probe_phases"][0]["phase"] == "decode"


def test_report_evidence_gate_fails_matrix_and_hardware_when_required(tmp_path: Path) -> None:
    report_path = _write_report(
        tmp_path,
        "telemetry",
        run_kind="serving_benchmark",
        telemetry_failures=["powermetrics_failed:fixture"],
        adapter_id="",
    )

    gate = build_report_evidence_gate(
        [report_path],
        require_release_matrix=True,
        require_hardware_telemetry=True,
    )

    assert gate["passed"] is False
    messages = [failure["message"] for failure in gate["blocking_failures"]]
    assert "hardware telemetry failure: candidate:telemetry-head:powermetrics_failed:fixture" in messages
    assert "release evidence matrix role is missing: dialogue_event_evaluation" in messages
    assert "release evidence matrix role is missing: adapter_check" in messages


def test_report_evidence_gate_script_writes_bundle_and_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report_path = _write_report(tmp_path, "serving", run_kind="serving_benchmark")
    output_dir = tmp_path / "gate"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "report_evidence_gate.py",
            "--report-json",
            str(report_path),
            "--output-dir",
            str(output_dir),
            "--json",
        ],
    )

    assert report_evidence_gate_script.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["passed"] is True
    assert (output_dir / "report-evidence-gate.json").is_file()
    assert (output_dir / "pr-evidence.md").is_file()


def test_report_evidence_gate_covers_invalid_payload_and_edge_summaries(tmp_path: Path) -> None:
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{", encoding="utf-8")
    array_json = tmp_path / "array.json"
    array_json.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="could not be decoded"):
        load_report_payload(bad_json)
    with pytest.raises(ValueError, match="must be an object"):
        load_report_payload(array_json)

    invalid_report = tmp_path / "invalid-report.json"
    invalid_report.write_text(
        json.dumps(
            {
                "schema_version": "melix.benchmark_evaluation_report.v1",
                "report_id": "invalid",
                "source_evidence_ids": ["bad-run"],
                "metrics": [{"metric": "adapter.load_ms", "result": "pass", "gate_policy": {}}],
                "probe_summary": {"baseline": [], "candidate": {}},
            }
        ),
        encoding="utf-8",
    )

    gate = build_report_evidence_gate(
        [invalid_report],
        matrix={"adapter_metric": {"metric_prefixes": ("adapter.",)}},
        require_hardware_telemetry=True,
    )

    assert gate["passed"] is False
    assert gate["release_matrix"][0]["present"] is True
    assert "telemetry_summary_missing" in gate["reports"][0]["telemetry_failures"]
    assert gate["reports"][0]["evidence_validity_metrics"] == {}
    assert gate["reports"][0]["slowest_probe_phases"] == []
    assert report_evidence_gate_module._probe_phases({"probe_summary": []}) == set()
    assert report_evidence_gate_module._dict_list({"not": "a list"}) == []

    markdown = render_pr_evidence_markdown(
        {
            **gate,
            "known_gaps": ["baseline_probe_timeline_missing"],
        }
    )
    assert "## Blocking Failures" in markdown
    assert "## Known Gaps" in markdown


def test_report_evidence_gate_script_handles_errors_and_failed_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["report_evidence_gate.py"])
    assert report_evidence_gate_script.main() == 2
    assert "at least one --report-json is required" in capsys.readouterr().err

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["report_evidence_gate.py", "--report-json", str(bad_json)],
    )
    assert report_evidence_gate_script.main() == 2
    assert "could not be decoded" in capsys.readouterr().err

    regression_report = _write_report(
        tmp_path,
        "regression-cli",
        run_kind="serving_benchmark",
        baseline_decode_ms=10.0,
        candidate_decode_ms=20.0,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["report_evidence_gate.py", "--report-json", str(regression_report)],
    )
    assert report_evidence_gate_script.main() == 1
    assert json.loads(capsys.readouterr().out)["passed"] is False
