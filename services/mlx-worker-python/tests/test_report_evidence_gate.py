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


def test_report_evidence_gate_slowest_probe_phases_keeps_top_five_order() -> None:
    slowest_phases: list[object] = [
        {"phase": f"phase-{index}", "duration_ms": float(index)}
        for index in range(20)
    ]
    slowest_phases.insert(0, {"phase": "missing-duration"})
    slowest_phases.insert(1, "not-a-phase-row")
    report: dict[str, object] = {
        "probe_summary": {
            "baseline": {"slowest_phases": "not-a-list"},
            "candidate": {"slowest_phases": slowest_phases},
        }
    }

    rows = report_evidence_gate_module._slowest_probe_phases(report)

    assert [row["duration_ms"] for row in rows] == [19.0, 18.0, 17.0, 16.0, 15.0]
    assert {row["side"] for row in rows} == {"candidate"}


def test_report_evidence_gate_slowest_probe_phases_preserves_tie_order() -> None:
    report: dict[str, object] = {
        "probe_summary": {
            "baseline": {
                "slowest_phases": [
                    {"phase": f"baseline-{index}", "duration_ms": 10.0}
                    for index in range(4)
                ]
            },
            "candidate": {
                "slowest_phases": [
                    {"phase": f"candidate-{index}", "duration_ms": 10.0}
                    for index in range(4)
                ]
            },
        }
    }

    rows = report_evidence_gate_module._slowest_probe_phases(report)

    assert [row["phase"] for row in rows] == [
        "baseline-0",
        "baseline-1",
        "baseline-2",
        "baseline-3",
        "candidate-0",
    ]


def test_report_evidence_gate_slowest_probe_phases_accepts_typed_durations() -> None:
    report: dict[str, object] = {
        "probe_summary": {
            "baseline": {
                "slowest_phases": [
                    {"phase": "float", "duration_ms": 4.0},
                    {"phase": "string", "duration_ms": "7.5"},
                    {"phase": "int", "duration_ms": 6},
                ]
            },
            "candidate": {
                "slowest_phases": [
                    {"phase": "empty", "duration_ms": ""},
                    {"phase": "missing"},
                    {"phase": "none", "duration_ms": None},
                ]
            },
        }
    }

    rows = report_evidence_gate_module._slowest_probe_phases(report)

    assert [row["phase"] for row in rows] == ["string", "int", "float", "empty", "missing"]


def test_report_evidence_gate_slowest_probe_phases_rank_boolean_duration_last() -> None:
    """A JSON ``true`` duration must not displace a real phase from the top five.

    ``bool`` subclasses ``int``, so an unguarded numeric check scores ``True`` as
    1.0 and drops the slowest genuine phase off the end of the list.
    """
    report: dict[str, object] = {
        "probe_summary": {
            "baseline": {
                "slowest_phases": [
                    {"phase": "bool_true", "duration_ms": True},
                    {"phase": "nine", "duration_ms": 9.0},
                    {"phase": "eight", "duration_ms": 8.0},
                    {"phase": "seven", "duration_ms": 7.0},
                    {"phase": "six", "duration_ms": 6.0},
                    {"phase": "half", "duration_ms": 0.5},
                ]
            }
        }
    }

    rows = report_evidence_gate_module._slowest_probe_phases(report)

    assert [row["phase"] for row in rows] == ["nine", "eight", "seven", "six", "half"]
    assert report_evidence_gate_module._probe_phase_duration_key(
        {"duration_ms": True}
    ) == 0.0
    assert report_evidence_gate_module._probe_phase_duration_key(
        {"duration_ms": False}
    ) == 0.0


def test_report_evidence_gate_run_kind_rules_accept_non_tuple_iterables() -> None:
    assert report_evidence_gate_module._rule_matches_report(
        rule={"run_kinds": {"evaluation", "serving_benchmark"}},
        run_kind_values={"serving_benchmark"},
        targets=[],
        metrics=[],
        probe_phases=set(),
    )
    assert not report_evidence_gate_module._rule_matches_report(
        rule={"run_kinds": {"evaluation"}},
        run_kind_values={"serving_benchmark"},
        targets=[],
        metrics=[],
        probe_phases=set(),
    )


def test_report_evidence_gate_run_kind_non_string_values_still_match_by_string() -> None:
    assert report_evidence_gate_module._rule_matches_report(
        rule={"run_kinds": ("42",)},
        run_kind_values={"42"},
        targets=[],
        metrics=[],
        probe_phases=set(),
    )


def test_report_evidence_gate_run_kind_values_preserve_exact_string_fast_path() -> None:
    class RunKind(str):
        pass

    values = report_evidence_gate_module._report_run_kind_values(
        [
            {"run_kind": "serving_benchmark"},
            {"run_kind": 42},
            {"run_kind": RunKind("dialogue_evaluation")},
            {},
        ]
    )

    assert values == {"serving_benchmark", "42", "dialogue_evaluation", ""}


def test_report_evidence_gate_matrix_roles_keep_non_string_run_kind_match() -> None:
    roles = report_evidence_gate_module._report_matrix_roles(
        {"runs": [{"run_kind": 42}]},
        {"numeric_run": {"run_kinds": ("42",)}},
    )

    assert roles == ["numeric_run"]


def test_report_evidence_gate_matrix_roles_select_multiple_run_kind_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_string_frozenset = report_evidence_gate_module._string_frozenset
    normalized_values: list[object] = []

    def count_string_frozenset(values: object) -> frozenset[str]:
        normalized_values.append(values)
        return original_string_frozenset(values)

    monkeypatch.setattr(report_evidence_gate_module, "_string_frozenset", count_string_frozenset)

    roles = report_evidence_gate_module._report_matrix_roles(
        {"runs": [{"run_kind": "serving_benchmark"}, {"run_kind": "evaluation"}]},
        {
            "serving": {"run_kinds": ("serving_benchmark",)},
            "evaluation": {"run_kinds": ("evaluation", "dialogue_evaluation")},
            "adapter": {"run_kinds": ("adapter_check",)},
        },
    )

    assert roles == ["serving", "evaluation"]
    assert normalized_values == [("evaluation", "dialogue_evaluation"), ("adapter_check",)]

    normalized_values.clear()
    mutable_roles = report_evidence_gate_module._report_matrix_roles(
        {"runs": [{"run_kind": "dynamic"}, {"run_kind": "99"}]},
        {
            "dynamic": {"run_kinds": {"dynamic"}},
            "numeric_rule": {"run_kinds": (99,)},
        },
    )
    assert mutable_roles == ["dynamic", "numeric_rule"]
    assert normalized_values == [{"dynamic"}]


class _UnstringableEvidenceId:
    def __str__(self) -> str:  # pragma: no cover - should not be called
        raise AssertionError("unmatched evidence IDs should not be normalized")


def test_report_evidence_gate_release_matrix_skips_evidence_id_normalization_for_unmatched_roles() -> None:
    rows = report_evidence_gate_module._release_matrix_rows(
        [
            {
                "release_matrix_roles": ["unmatched", "also_unmatched"],
                "source_evidence_ids": [_UnstringableEvidenceId()],
            }
        ],
        {"serving": {"run_kinds": ("serving_benchmark",), "description": "serving"}},
    )

    assert rows == [
        {
            "role": "serving",
            "required": True,
            "present": False,
            "evidence_ids": [],
            "description": "serving",
        }
    ]


def test_report_evidence_gate_metric_prefix_preserves_non_string_match() -> None:
    assert report_evidence_gate_module._rule_matches_report(
        rule={"metric_prefixes": ("42",)},
        run_kind_values=set(),
        targets=[],
        metrics=[{"metric": 42}],
        probe_phases=set(),
    )


def test_report_evidence_gate_metric_prefix_list_rules_reflect_mutation() -> None:
    metric_prefixes = ["adapter."]
    rule = {"metric_prefixes": metric_prefixes}

    assert not report_evidence_gate_module._rule_matches_report(
        rule=rule,
        run_kind_values=set(),
        targets=[],
        metrics=[{"metric": "runtime.decode_ms"}],
        probe_phases=set(),
    )
    metric_prefixes.append("runtime.")
    assert report_evidence_gate_module._rule_matches_report(
        rule=rule,
        run_kind_values=set(),
        targets=[],
        metrics=[{"metric": "runtime.decode_ms"}],
        probe_phases=set(),
    )


def test_report_evidence_gate_target_field_sparse_match_scans_row_items() -> None:
    class SparseTarget(dict[str, object]):
        missing_getitem_calls = 0

        def __getitem__(self, key: str) -> object:  # pragma: no cover - regression guard
            if key not in self:
                type(self).missing_getitem_calls += 1
                raise AssertionError(f"unexpected missing target lookup: {key}")
            return super().__getitem__(key)

    rule: dict[str, object] = {
        "target_fields": tuple(f"unused_{index}" for index in range(64)) + ("adapter_id",)
    }
    target = SparseTarget({"adapter_id": "adapter-a"})

    assert report_evidence_gate_module._rule_matches_report(
        rule=rule,
        run_kind_values=set(),
        targets=[target],
        metrics=[],
        probe_phases=set(),
    )
    assert SparseTarget.missing_getitem_calls == 0


def test_report_evidence_gate_target_field_list_rules_reflect_mutation() -> None:
    target_fields = ["adapter_id"]
    rule = {"target_fields": target_fields}

    assert not report_evidence_gate_module._rule_matches_report(
        rule=rule,
        run_kind_values=set(),
        targets=[{"adapter_snapshot": "snapshot-a"}],
        metrics=[],
        probe_phases=set(),
    )
    target_fields.append("adapter_snapshot")
    assert report_evidence_gate_module._rule_matches_report(
        rule=rule,
        run_kind_values=set(),
        targets=[{"adapter_snapshot": "snapshot-a"}],
        metrics=[],
        probe_phases=set(),
    )


def test_report_evidence_gate_target_field_preserves_stringified_presence() -> None:
    rule = {"target_fields": ("adapter_id", "adapter_snapshot")}

    assert not report_evidence_gate_module._rule_matches_report(
        rule=rule,
        run_kind_values=set(),
        targets=[{"adapter_id": "   "}],
        metrics=[],
        probe_phases=set(),
    )
    assert report_evidence_gate_module._rule_matches_report(
        rule=rule,
        run_kind_values=set(),
        targets=[{"adapter_id": None}],
        metrics=[],
        probe_phases=set(),
    )
    assert report_evidence_gate_module._rule_matches_report(
        rule=rule,
        run_kind_values=set(),
        targets=[{"adapter_id": 0}],
        metrics=[],
        probe_phases=set(),
    )
    assert not report_evidence_gate_module._rule_matches_report(
        rule=rule,
        run_kind_values=set(),
        targets=[{"unrelated_field": 0}],
        metrics=[],
        probe_phases=set(),
    )


def test_report_evidence_gate_has_text_exact_string_fast_path_preserves_whitespace_semantics() -> None:
    assert report_evidence_gate_module._has_text("adapter-a")
    assert report_evidence_gate_module._has_text(" adapter-a")
    assert report_evidence_gate_module._has_text("adapter-a ")
    assert not report_evidence_gate_module._has_text("")
    assert not report_evidence_gate_module._has_text("   ")


def test_report_evidence_gate_target_field_preserves_string_subclass_strip() -> None:
    class BlankWhenStripped(str):
        def strip(self, chars: str | None = None) -> str:  # pragma: no cover - regression guard
            return ""

    assert not report_evidence_gate_module._rule_matches_report(
        rule={"target_fields": ("adapter_id",)},
        run_kind_values=set(),
        targets=[{"adapter_id": BlankWhenStripped("adapter-a")}],
        metrics=[],
        probe_phases=set(),
    )


def test_report_evidence_gate_probe_phase_list_rules_reflect_mutation() -> None:
    probe_phases = ["runtime_prepare", "model_load", "decode", "embedding"]
    rule = {"probe_phases": probe_phases}

    assert not report_evidence_gate_module._rule_matches_report(
        rule=rule,
        run_kind_values=set(),
        targets=[],
        metrics=[],
        probe_phases={"runtime_prepare", "model_load", "decode"},
    )
    probe_phases.pop()
    assert report_evidence_gate_module._rule_matches_report(
        rule=rule,
        run_kind_values=set(),
        targets=[],
        metrics=[],
        probe_phases={"runtime_prepare", "model_load", "decode"},
    )


def test_report_evidence_gate_empty_probe_phase_rules_skip_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_string_frozenset(values: object) -> frozenset[str]:  # pragma: no cover
        raise AssertionError("empty probe phase rules should skip set normalization")

    monkeypatch.setattr(report_evidence_gate_module, "_string_frozenset", fail_string_frozenset)

    assert not report_evidence_gate_module._rule_matches_report(
        rule={},
        run_kind_values=set(),
        targets=[],
        metrics=[],
        probe_phases={"runtime_prepare"},
    )
    assert not report_evidence_gate_module._rule_matches_report(
        rule={"probe_phases": ()},
        run_kind_values=set(),
        targets=[],
        metrics=[],
        probe_phases={"runtime_prepare"},
    )


def test_report_matrix_roles_materializes_targets_and_metrics_for_mixed_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    original_dict_list = report_evidence_gate_module._dict_list

    def count_dict_list(value: object) -> list[dict[str, object]]:
        calls.append(value)
        return original_dict_list(value)

    monkeypatch.setattr(report_evidence_gate_module, "_dict_list", count_dict_list)

    roles = report_evidence_gate_module._report_matrix_roles(
        {
            "runs": [{"run_kind": "serving_benchmark"}],
            "targets": [{"adapter_id": "adapter-a"}],
            "metrics": [{"metric": "adapter.loss"}],
        },
        {
            "serving": {"run_kinds": ("serving_benchmark",)},
            "adapter_metric": {"metric_prefixes": ("adapter.",)},
            "adapter_target": {"target_fields": ("adapter_id",)},
        },
    )

    assert roles == ["serving", "adapter_metric", "adapter_target"]
    assert calls == [
        [{"run_kind": "serving_benchmark"}],
        [{"adapter_id": "adapter-a"}],
        [{"metric": "adapter.loss"}],
    ]


def test_report_evidence_gate_probe_phases_keeps_blank_and_padded_string_semantics() -> None:
    phases = report_evidence_gate_module._probe_phases(
        {
            "probe_summary": {
                "baseline": {
                    "slowest_phases": [
                        {"phase": "runtime_prepare"},
                        {"phase": " runtime_prepare "},
                        {"phase": "   "},
                    ],
                    "failed_phases": [{"phase": "decode"}],
                }
            }
        }
    )

    assert phases == {"runtime_prepare", "decode"}


def test_report_evidence_gate_probe_phases_preserves_dict_subclass_rows() -> None:
    class PhaseRow(dict[str, object]):
        pass

    phases = report_evidence_gate_module._probe_phases(
        {
            "probe_summary": {
                "baseline": {
                    "slowest_phases": [
                        PhaseRow(phase=" runtime_prepare "),
                        PhaseRow(phase="runtime_prepare"),
                    ]
                }
            }
        }
    )

    assert phases == {"runtime_prepare"}


def test_report_evidence_gate_run_kind_list_rules_reflect_mutation() -> None:
    run_kinds = ["evaluation"]
    rule = {"run_kinds": run_kinds}

    assert not report_evidence_gate_module._rule_matches_report(
        rule=rule,
        run_kind_values={"serving_benchmark"},
        targets=[],
        metrics=[],
        probe_phases=set(),
    )
    run_kinds.append("serving_benchmark")
    assert report_evidence_gate_module._rule_matches_report(
        rule=rule,
        run_kind_values={"serving_benchmark"},
        targets=[],
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
    release_matrix = gate["release_matrix"]
    assert isinstance(release_matrix, list)
    serving_row = next(row for row in release_matrix if row["role"] == "serving_benchmark")
    assert serving_row["evidence_ids"] == ["serving-base", "serving-head"]
    markdown = render_pr_evidence_markdown(gate)
    assert "Report JSON" in markdown
    assert "serving-head" in markdown


def test_report_evidence_gate_release_matrix_dedupes_evidence_ids(tmp_path: Path) -> None:
    serving_report = _write_report(tmp_path, "serving", run_kind="serving_benchmark")

    gate = build_report_evidence_gate(
        [serving_report, serving_report],
        matrix={"serving": {"run_kinds": ("serving_benchmark",)}},
    )

    assert gate["release_matrix"] == [
        {
            "role": "serving",
            "required": True,
            "present": True,
            "evidence_ids": ["serving-base", "serving-head"],
            "description": "",
        }
    ]


def test_report_evidence_gate_release_matrix_ignores_invalid_cached_roles() -> None:
    rows = report_evidence_gate_module._release_matrix_rows(
        [
            {"release_matrix_roles": "serving", "source_evidence_ids": ["bad-type"]},
            {"release_matrix_roles": ["serving"], "source_evidence_ids": "bad-type"},
            {"release_matrix_roles": ["serving"], "source_evidence_ids": []},
            {"release_matrix_roles": ["serving", "unknown"], "source_evidence_ids": ["ok"]},
        ],
        {"serving": {"description": "serving evidence"}},
    )

    assert rows == [
        {
            "role": "serving",
            "required": True,
            "present": True,
            "evidence_ids": ["ok"],
            "description": "serving evidence",
        }
    ]


def test_report_evidence_gate_release_matrix_fast_paths_empty_evidence() -> None:
    rows = report_evidence_gate_module._release_matrix_rows(
        [
            {"release_matrix_roles": ["unknown"], "source_evidence_ids": ["ignored"]},
            {"release_matrix_roles": ["serving"], "source_evidence_ids": []},
        ],
        {
            "serving": {"description": "serving evidence"},
            "adapter": {"required": False, "description": "adapter evidence"},
        },
    )

    assert rows == [
        {
            "role": "serving",
            "required": True,
            "present": False,
            "evidence_ids": [],
            "description": "serving evidence",
        },
        {
            "role": "adapter",
            "required": False,
            "present": False,
            "evidence_ids": [],
            "description": "adapter evidence",
        },
    ]


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
    dict_rows = [{"phase": "setup"}, {"phase": "probe"}]
    assert report_evidence_gate_module._dict_list(dict_rows) == dict_rows
    assert report_evidence_gate_module._dict_list(dict_rows) is dict_rows
    assert report_evidence_gate_module._dict_list([dict_rows[0], "skip", dict_rows[1]]) == dict_rows

    class DictRow(dict[str, object]):
        pass

    subclass_rows: list[object] = [DictRow({"phase": "subclass"}), {"phase": "plain"}]
    assert report_evidence_gate_module._dict_list(subclass_rows) == subclass_rows

    class RowList(list[object]):
        pass

    subclass_list = RowList([{"phase": "plain"}, DictRow({"phase": "subclass"})])
    assert report_evidence_gate_module._dict_list(subclass_list) == subclass_list
    assert report_evidence_gate_module._dict_list(RowList([subclass_list[0], "skip"])) == [
        subclass_list[0]
    ]

    markdown = render_pr_evidence_markdown(
        {
            **gate,
            "known_gaps": ["baseline_probe_timeline_missing"],
        }
    )
    assert "## Blocking Failures" in markdown
    assert "## Known Gaps" in markdown


def test_load_report_payload_reads_json_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_bytes(b'{"schema_version":"fixture","value":3}')

    def fail_read_text(self: Path, *args: object, **kwargs: object) -> str:
        raise AssertionError(f"unexpected text decode for {self}")

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    assert load_report_payload(report_path) == {"schema_version": "fixture", "value": 3}


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
