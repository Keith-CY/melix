from __future__ import annotations

import json
from pathlib import Path
import runpy
import sys

import pytest

from worker.productization.pr_scoped_performance import (
    _build_large_benchmark_bundle,
    _build_large_training_dataset_samples,
    _build_metric_row,
    _build_probe_report_row,
    _build_probe_details,
    _closure_index_text,
    _dict_list,
    _dispatch_probe_impl,
    _float_or_none,
    _format_delta,
    _format_value,
    _is_relative_to,
    _load_repo_module,
    _markdown_cell,
    _matches_any_glob,
    _parse_coverage_percent,
    _probe_benchmark_evaluation_report,
    _probe_closure_audit,
    _probe_evaluation_job_id,
    _probe_training_dataset_token_percentiles,
    _probe_command_json,
    _run_command,
    _run_head_verification,
    _run_probe_impl,
    _seed_closure_audit_repo,
    _string_list,
    _write,
    MetricDefinition,
    ProbeDefinition,
    build_performance_report,
    build_scope_report,
    build_sticky_comment_body,
    load_probe_registry,
    render_markdown_report,
    render_terminal_report,
    run_probe_job,
    write_report_outputs,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = REPO_ROOT / "infra/perf/pr_scoped_probes.json"


@pytest.fixture()
def benchmark_scope() -> dict[str, object]:
    return build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py"],
    )


def test_scope_report_selects_only_matching_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/productization/closure_audit.py"],
    )

    assert scope["selected_count"] == 1
    selected_probe = scope["selected_probes"][0]
    assert selected_probe["id"] == "closure-audit-probe-source-short-circuit"
    assert scope["force_all"] is False


def test_scope_report_selects_training_dataset_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/model_ops/training_dataset.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "training-dataset-token-percentiles-single-sort"


def test_scope_report_selects_evaluation_job_id_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/engine/evaluation_core.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "evaluation-job-id-high-water-mark"


def test_scope_report_force_selects_all_on_infra_change() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["infra/perf/pr_scoped_probes.json"],
    )

    assert scope["force_all"] is True
    assert scope["selected_count"] == len(load_probe_registry(REGISTRY_PATH))


def test_registered_probes_expose_focused_commands() -> None:
    for probe in load_probe_registry(REGISTRY_PATH):
        assert probe.test_command
        assert probe.coverage_command
        assert probe.probe_command


def test_scope_report_with_no_matching_probe_returns_empty_selection() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["README.md"],
    )

    assert scope["selected_count"] == 0
    assert scope["selected_probes"] == []


def test_load_probe_registry_rejects_invalid_payloads(tmp_path: Path) -> None:
    invalid_root = tmp_path / "invalid-root.json"
    invalid_root.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON list"):
        load_probe_registry(invalid_root)

    invalid_entry = tmp_path / "invalid-entry.json"
    invalid_entry.write_text(json.dumps(["bad"]), encoding="utf-8")
    with pytest.raises(ValueError, match="JSON objects"):
        load_probe_registry(invalid_entry)

    invalid_metrics = tmp_path / "invalid-metrics.json"
    invalid_metrics.write_text(
        json.dumps([
            {
                "id": "demo",
                "name": "Demo",
                "probe_impl": "benchmark_evaluation_report",
                "metrics": [],
            }
        ]),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="non-empty list"):
        load_probe_registry(invalid_metrics)


def test_probe_smokes_return_metrics_against_current_repo() -> None:
    benchmark_metrics = _probe_benchmark_evaluation_report(REPO_ROOT)
    closure_metrics = _probe_closure_audit(REPO_ROOT)
    evaluation_job_id_metrics = _probe_evaluation_job_id(REPO_ROOT)
    training_dataset_metrics = _probe_training_dataset_token_percentiles(REPO_ROOT)

    assert benchmark_metrics["elapsed_ms_mean"] > 0
    assert benchmark_metrics["peak_bytes_mean"] > 0
    assert benchmark_metrics["row_count"] > 0
    assert closure_metrics["elapsed_ms_mean"] > 0
    assert closure_metrics["probe_file_reads_mean"] > 0
    assert closure_metrics["finding_count"] > 0
    assert evaluation_job_id_metrics["elapsed_ms_mean"] > 0
    assert evaluation_job_id_metrics["per_call_ms_mean"] > 0
    assert evaluation_job_id_metrics["allocation_count"] == 200.0
    assert evaluation_job_id_metrics["first_job_id_numeric"] == 2001.0
    assert evaluation_job_id_metrics["last_job_id_numeric"] == 2200.0
    assert training_dataset_metrics["elapsed_ms_mean"] > 0
    assert training_dataset_metrics["sample_count"] == 20000.0
    assert training_dataset_metrics["prompt_tokens_p95"] > 0
    assert training_dataset_metrics["total_tokens_p95"] > 0


def test_dispatch_probe_impl_supports_evaluation_job_id_probe() -> None:
    probe = ProbeDefinition(
        probe_id="evaluation-job-id-high-water-mark",
        name="Evaluation job-id high-water mark",
        runner="ubuntu-latest",
        watch_globs=("services/mlx-worker-python/worker/engine/evaluation_core.py",),
        test_command="true",
        coverage_command="true",
        probe_impl="evaluation_job_id",
        metrics=(MetricDefinition(key="elapsed_ms_mean", unit="ms", direction="lower_is_better"),),
    )

    metrics = _dispatch_probe_impl(probe=probe, repo_root=REPO_ROOT)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["per_call_ms_mean"] > 0


def test_run_probe_job_executes_verification_and_probe_for_current_repo() -> None:
    result, success = run_probe_job(
        registry_path=REGISTRY_PATH,
        probe_id="benchmark-evaluation-report-running-aggregates",
        base_repo=REPO_ROOT,
        head_repo=REPO_ROOT,
    )

    assert success is True
    assert result["head_verification"]["test"]["ok"] is True
    assert result["head_verification"]["coverage"]["coverage_pct"] >= 95.0
    assert result["base_probe"]["metrics"]["elapsed_ms_mean"] > 0


def test_report_rendering_marks_regressions_and_builds_sticky_comment(
    benchmark_scope: dict[str, object],
) -> None:
    result = {
        "probe": benchmark_scope["selected_probes"][0],
        "head_verification": {
            "test": {"ok": True, "coverage_pct": None},
            "coverage": {"ok": True, "coverage_pct": 97.0},
        },
        "base_probe": {
            "ok": True,
            "metrics": {
                "elapsed_ms_mean": 10.0,
                "peak_bytes_mean": 100.0,
            },
        },
        "head_probe": {
            "ok": True,
            "metrics": {
                "elapsed_ms_mean": 12.0,
                "peak_bytes_mean": 120.0,
            },
        },
    }

    report = build_performance_report(scope=benchmark_scope, probe_results=[result])
    markdown = render_markdown_report(report)
    terminal = render_terminal_report(report)
    sticky = build_sticky_comment_body(markdown)

    assert report["summary"]["status"] == "regression"
    assert report["summary"]["regression_count"] == 1
    assert "Melix PR Scoped Performance Report" in markdown
    assert "regression" in terminal
    assert sticky.startswith("<!-- melix-pr-scoped-performance-report -->\n")
    assert json.loads(json.dumps(report))["summary"]["selected_probe_count"] == 1


def test_report_handles_missing_results_and_empty_probe_selection(tmp_path: Path) -> None:
    scope = {
        "changed_files": ["README.md"],
        "force_all": False,
        "selected_count": 1,
        "selected_probes": [{"id": "missing", "name": "Missing probe", "metrics": []}],
    }
    report = build_performance_report(scope=scope, probe_results=[])
    outputs = write_report_outputs(report, tmp_path / "report")

    assert report["summary"]["status"] == "verification_failed"
    assert outputs["json"].is_file()
    assert outputs["markdown"].is_file()

    empty_report = build_performance_report(
        scope={"changed_files": [], "force_all": False, "selected_count": 0, "selected_probes": []},
        probe_results=[],
    )
    assert "No registered performance probes were selected" in render_markdown_report(empty_report)
    assert "No registered performance probes were selected" in render_terminal_report(empty_report)


def test_metric_and_probe_helpers_cover_error_branches() -> None:
    missing = _build_metric_row(
        key="elapsed_ms_mean",
        unit="ms",
        direction="lower_is_better",
        warn_pct=5.0,
        base_metrics={},
        head_metrics={},
    )
    higher_is_better = _build_metric_row(
        key="score",
        unit="ratio",
        direction="higher_is_better",
        warn_pct=5.0,
        base_metrics={"score": 10.0},
        head_metrics={"score": 8.0},
    )
    zero_baseline = _build_metric_row(
        key="count",
        unit="count",
        direction="lower_is_better",
        warn_pct=0.0,
        base_metrics={"count": 0.0},
        head_metrics={"count": 1.0},
    )

    assert missing["status"] == "missing"
    assert higher_is_better["status"] == "regression"
    assert zero_baseline["delta_pct"] is None

    probe_result = {
        "probe": {"id": "demo", "name": "Demo", "metrics": [{"key": "score", "unit": "ms", "direction": "lower_is_better", "warn_pct": 5.0}]},
        "head_verification": {
            "test": {"ok": False},
            "coverage": {"ok": False, "coverage_pct": None},
        },
        "base_probe": {"ok": False, "error": "base boom", "metrics": {}},
        "head_probe": {"ok": False, "error": "head boom", "metrics": {}},
    }
    row = _build_probe_report_row(probe_result)

    assert row["status"] == "verification_failed"
    assert "Targeted tests failed." in _build_probe_details(result=probe_result)
    assert "Coverage command failed." in _build_probe_details(result=probe_result)
    assert "base boom" in _build_probe_details(result=probe_result)
    assert "head boom" in _build_probe_details(result=probe_result)


def test_command_and_verification_helpers_cover_skip_and_failure_paths(tmp_path: Path) -> None:
    coverage_stdout = "TOTAL  10  0  100%\n"
    command_result = _run_command(
        "python -c \"print('TOTAL  10  0  100%')\"",
        cwd=tmp_path,
    )
    assert command_result["coverage_pct"] == 100.0
    assert _parse_coverage_percent(coverage_stdout) == 100.0
    assert _parse_coverage_percent("no total line\n") is None

    probe = ProbeDefinition(
        probe_id="demo",
        name="Demo",
        runner="ubuntu-latest",
        watch_globs=("*.py",),
        test_command="python -c \"raise SystemExit(1)\"",
        coverage_command="python -c \"print('should not run')\"",
        probe_impl="benchmark_evaluation_report",
        probe_command="",
        metrics=(MetricDefinition(key="elapsed_ms_mean", unit="ms", direction="lower_is_better"),),
    )
    verification = _run_head_verification(probe=probe, repo_root=tmp_path)

    assert verification["test"]["ok"] is False
    assert verification["coverage"]["stderr"].startswith("Skipped because")


def test_command_json_probe_executes_probe_command_and_parses_metrics(tmp_path: Path) -> None:
    probe = ProbeDefinition(
        probe_id="command-json",
        name="Command JSON",
        runner="macos-15",
        watch_globs=("Sources/**/*.swift",),
        test_command="true",
        coverage_command="true",
        probe_impl="command_json",
        probe_command=(
            "python3 -c \"import json; "
            "print(json.dumps({'elapsed_ms_mean': 12.5, 'iteration_count': 3}))\""
        ),
        metrics=(MetricDefinition(key="elapsed_ms_mean", unit="ms", direction="lower_is_better"),),
    )

    metrics = _probe_command_json(probe=probe, repo_root=tmp_path)

    assert metrics == {"elapsed_ms_mean": 12.5, "iteration_count": 3.0}


def test_command_json_probe_rejects_missing_command_and_non_numeric_metrics(tmp_path: Path) -> None:
    missing = ProbeDefinition(
        probe_id="missing",
        name="Missing",
        runner="ubuntu-latest",
        watch_globs=(),
        test_command="true",
        coverage_command="true",
        probe_impl="command_json",
        probe_command="",
        metrics=(MetricDefinition(key="x", unit="ms", direction="lower_is_better"),),
    )
    with pytest.raises(ValueError, match="probe_command"):
        _probe_command_json(probe=missing, repo_root=tmp_path)

    non_numeric = ProbeDefinition(
        probe_id="bad-json",
        name="Bad JSON",
        runner="ubuntu-latest",
        watch_globs=(),
        test_command="true",
        coverage_command="true",
        probe_impl="command_json",
        probe_command="python3 -c \"print('{\\\"elapsed_ms_mean\\\": \\\"slow\\\"}')\"",
        metrics=(MetricDefinition(key="elapsed_ms_mean", unit="ms", direction="lower_is_better"),),
    )
    with pytest.raises(ValueError, match="numeric"):
        _probe_command_json(probe=non_numeric, repo_root=tmp_path)


def test_dispatch_and_module_loading_helpers_cover_failure_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported probe implementation"):
        _dispatch_probe_impl(
            probe=ProbeDefinition(
                probe_id="bad",
                name="Bad",
                runner="ubuntu-latest",
                watch_globs=(),
                test_command="true",
                coverage_command="true",
                probe_impl="unsupported",
                probe_command="",
                metrics=(MetricDefinition(key="x", unit="ms", direction="lower_is_better"),),
            ),
            repo_root=tmp_path,
        )

    broken = _run_probe_impl(
        probe=ProbeDefinition(
            probe_id="bad",
            name="Bad",
            runner="ubuntu-latest",
            watch_globs=(),
            test_command="true",
            coverage_command="true",
            probe_impl="unsupported",
            probe_command="",
            metrics=(MetricDefinition(key="x", unit="ms", direction="lower_is_better"),),
        ),
        repo_root=tmp_path,
        repo_label="head",
    )
    assert broken["ok"] is False

    missing_module = tmp_path / "missing.py"
    with pytest.raises(ValueError, match="could not load module"):
        _load_repo_module(missing_module, unique_name="missing")

    module_path = tmp_path / "demo_module.py"
    module_path.write_text("VALUE = 7\n", encoding="utf-8")
    module = _load_repo_module(module_path, unique_name="demo_module")
    assert module.VALUE == 7


def test_data_generation_and_formatting_helpers_cover_misc_branches(tmp_path: Path) -> None:
    bundle = _build_large_benchmark_bundle(base_value=42.0)
    training_samples = _build_large_training_dataset_samples()
    assert len(bundle["benchmark_results"]) == 250
    assert len(bundle["benchmark_context_rows"]) == 900
    assert len(bundle["benchmark_matrix_request_rows"]) == 1200
    assert len(training_samples) == 20000
    assert all("prompt" in sample and "completion" in sample for sample in training_samples[:3])

    seeded_root = _seed_closure_audit_repo(tmp_path)
    assert (seeded_root / "docs/plans/2026-03-30-full-capability-roadmap-execution-index.md").is_file()
    assert "M9.8" in _closure_index_text()

    nested_path = tmp_path / "nested" / "file.txt"
    _write(nested_path, "hello\n")
    assert nested_path.read_text(encoding="utf-8") == "hello\n"

    assert _format_value(1.25) == "1.250"
    assert _format_value(3) == "3"
    assert _format_value(None) == "-"
    assert _format_delta({"delta": None, "delta_pct": None}) == "-"
    assert _format_delta({"delta": 2.5, "delta_pct": None}) == "+2.500"
    assert _format_delta({"delta": 2.5, "delta_pct": 10.0}) == "+2.500 (+10.00%)"
    assert _markdown_cell("a|b") == "a\\|b"
    assert _dict_list([{"ok": True}, 1]) == [{"ok": True}]
    assert _dict_list("not-a-list") == []
    assert _string_list([1, "two"]) == ["1", "two"]
    assert _string_list("not-a-list") == []
    assert _float_or_none(True) == 1.0
    assert _float_or_none(False) == 0.0
    assert _float_or_none("x") is None
    assert _matches_any_glob("services/a.py", ("services/*.py",)) is True
    assert _matches_any_glob("docs/a.md", ("services/*.py",)) is False
    assert _is_relative_to(nested_path, tmp_path) is True
    assert _is_relative_to(Path("/tmp/not-child"), tmp_path) is False


def test_cli_scripts_smoke(tmp_path: Path, benchmark_scope: dict[str, object], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    changed_files_path = tmp_path / "changed-files.json"
    changed_files_path.write_text(json.dumps(["services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py"]), encoding="utf-8")
    scope_output = tmp_path / "scope.json"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pr_scoped_performance_scope.py",
            "--registry",
            str(REGISTRY_PATH),
            "--changed-files-json",
            str(changed_files_path),
            "--output",
            str(scope_output),
        ],
    )
    scope_script = runpy.run_path(str(REPO_ROOT / "scripts/pr_scoped_performance_scope.py"))
    assert scope_script["main"]() == 0
    assert json.loads(scope_output.read_text(encoding="utf-8"))["selected_count"] == 1
    capsys.readouterr()

    probe_output = tmp_path / "probe.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pr_scoped_performance_run.py",
            "--registry",
            str(REGISTRY_PATH),
            "--probe-id",
            "benchmark-evaluation-report-running-aggregates",
            "--base-repo",
            str(REPO_ROOT),
            "--head-repo",
            str(REPO_ROOT),
            "--output",
            str(probe_output),
        ],
    )
    run_script = runpy.run_path(str(REPO_ROOT / "scripts/pr_scoped_performance_run.py"))
    assert run_script["main"]() == 0
    assert json.loads(probe_output.read_text(encoding="utf-8"))["probe"]["id"] == (
        "benchmark-evaluation-report-running-aggregates"
    )
    capsys.readouterr()

    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "probe.json").write_text(probe_output.read_text(encoding="utf-8"), encoding="utf-8")
    report_dir = tmp_path / "report"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pr_scoped_performance_report.py",
            "--scope",
            str(scope_output),
            "--results-dir",
            str(results_dir),
            "--output-dir",
            str(report_dir),
            "--format",
            "markdown",
            "--sticky-comment",
        ],
    )
    report_script = runpy.run_path(str(REPO_ROOT / "scripts/pr_scoped_performance_report.py"))
    assert report_script["main"]() == 0
    output = capsys.readouterr().out
    assert output.startswith("<!-- melix-pr-scoped-performance-report -->\n")
    assert (report_dir / "report.json").is_file()
