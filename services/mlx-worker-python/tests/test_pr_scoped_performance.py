from __future__ import annotations

import json
import os
from pathlib import Path
import runpy
import sys

import pytest
import worker.productization.pr_scoped_performance as pr_scoped_performance_module

from worker.productization.pr_scoped_performance import (
    _build_large_benchmark_bundle,
    _build_large_scope_probe_changed_files,
    _build_large_training_dataset_quality_samples,
    _build_large_training_dataset_samples,
    _build_metric_row,
    _single_pass_sample_iterable,
    _build_probe_report_row,
    _build_probe_details,
    _closure_index_text,
    _compiled_glob_pattern,
    _dict_list,
    _dispatch_probe_impl,
    _float_or_none,
    _format_delta,
    _format_value,
    _is_relative_to,
    _load_upload_receipt_pipeline_module,
    _load_repo_module,
    _markdown_cell,
    _matches_any_glob,
    _match_probe_indexes,
    _parse_coverage_percent,
    _probe_benchmark_evaluation_report,
    _probe_benchmark_export_run_scan,
    _probe_closure_audit,
    _probe_deterministic_rerank_query_context_reuse,
    _probe_evaluation_job_id,
    _probe_evaluation_sample_probe_aggregation,
    _probe_evaluation_store_compare_summary_csv_streaming,
    _probe_evaluation_store_samples_csv_streaming,
    _probe_pr_scoped_scope_matcher,
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


def test_scope_report_selects_evaluation_probes() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/engine/evaluation_core.py"],
    )

    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert scope["selected_count"] == 2
    assert probe_ids == {
        "evaluation-job-id-high-water-mark",
        "evaluation-sample-probe-aggregation",
    }


def test_scope_report_selects_evaluation_store_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/productization/evaluation_store.py"],
    )

    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert scope["selected_count"] == 2
    assert probe_ids == {
        "evaluation-store-compare-summary-csv-streaming",
        "evaluation-store-samples-csv-streaming",
    }


def test_scope_report_selects_worker_registry_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/registry.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "worker-registry-resident-bytes-accumulator"


def test_scope_report_selects_job_registry_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/model_ops/job_registry.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "job-registry-derived-model-single-pass"


def test_scope_report_selects_deterministic_rerank_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/runtime/deterministic_rerank_runtime.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "deterministic-rerank-query-context-reuse"


def test_scope_report_selects_benchmark_export_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/productization/benchmark_export.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "benchmark-export-run-scan-single-pass"


def test_scope_report_selects_benchmark_store_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/productization/benchmark_store.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "benchmark-store-matrix-streaming"


def test_scope_report_selects_bench_report_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/engine/maintenance_core.py"],
    )

    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert "maintenance-bench-report-readback" in probe_ids


def test_scope_report_selects_upload_receipt_published_files_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/model_ops/upload_receipt_pipeline.py"],
    )

    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert "upload-receipt-published-files-scandir" in probe_ids


def test_scope_report_selects_download_pipeline_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/model_ops/download_pipeline.py"],
    )

    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert "download-pipeline-directory-size-single-stat" in probe_ids


def test_scope_report_selects_performance_report_results_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["scripts/pr_scoped_performance_report.py"],
    )

    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert "pr-scoped-performance-report-results-scandir" in probe_ids


def test_scope_report_selects_package_macos_resolve_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["scripts/package_macos_menubar_app.py"],
    )

    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert "package-macos-resolve-fallback-scandir" in probe_ids


def test_scope_report_selects_dev_up_mlx_metal_dist_info_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["scripts/dev_up.py"],
    )

    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert "dev-up-mlx-metal-dist-info-scandir" in probe_ids


def test_scope_report_force_selects_all_on_infra_change() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["infra/perf/pr_scoped_probes.json"],
    )

    assert scope["force_all"] is True
    assert scope["selected_count"] == len(load_probe_registry(REGISTRY_PATH))
    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert "pr-scoped-performance-scope-matcher" in probe_ids


def test_scope_report_large_changed_set_preserves_exact_selection_semantics() -> None:
    changed_files = _build_large_scope_probe_changed_files() + [
        "services/mlx-worker-python/worker/engine/evaluation_core.py",
        "",
        "README.md",
    ]

    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=changed_files,
    )

    assert scope["force_all"] is False
    assert scope["changed_files"] == sorted({path for path in changed_files if path})
    assert [probe["id"] for probe in scope["selected_probes"]] == [
        "benchmark-export-run-scan-single-pass",
        "evaluation-job-id-high-water-mark",
        "evaluation-sample-probe-aggregation",
        "download-pipeline-directory-size-single-stat",
    ]
    assert scope["selected_count"] == 4


def test_match_probe_indexes_deduplicates_repeated_watch_globs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probes = (
        ProbeDefinition(
            probe_id="alpha",
            name="Alpha",
            runner="ubuntu-latest",
            watch_globs=("services/a.py", "shared.py"),
            test_command="true",
            coverage_command="true",
            probe_impl="benchmark_evaluation_report",
            probe_command="",
            metrics=(MetricDefinition(key="elapsed_ms_mean", unit="ms", direction="lower_is_better"),),
        ),
        ProbeDefinition(
            probe_id="beta",
            name="Beta",
            runner="ubuntu-latest",
            watch_globs=("shared.py", "services/*.py"),
            test_command="true",
            coverage_command="true",
            probe_impl="benchmark_evaluation_report",
            probe_command="",
            metrics=(MetricDefinition(key="elapsed_ms_mean", unit="ms", direction="lower_is_better"),),
        ),
        ProbeDefinition(
            probe_id="gamma",
            name="Gamma",
            runner="ubuntu-latest",
            watch_globs=("shared.py",),
            test_command="true",
            coverage_command="true",
            probe_impl="benchmark_evaluation_report",
            probe_command="",
            metrics=(MetricDefinition(key="elapsed_ms_mean", unit="ms", direction="lower_is_better"),),
        ),
    )
    calls: list[tuple[str, str]] = []

    def fake_glob_matches_path(path: str, glob: str) -> bool:
        calls.append((path, glob))
        return path == "services/b.py" and glob == "services/*.py"

    monkeypatch.setattr(pr_scoped_performance_module, "_glob_matches_path", fake_glob_matches_path)

    matched = _match_probe_indexes(changed_paths=("shared.py", "services/b.py", "unmatched.py"), probes=probes)

    assert matched == {0, 1, 2}
    assert calls == [
        ("shared.py", "services/*.py"),
        ("services/b.py", "services/*.py"),
        ("unmatched.py", "services/*.py"),
    ]


def test_compiled_glob_pattern_reuses_cached_regex() -> None:
    assert _compiled_glob_pattern("services/*.py") is _compiled_glob_pattern("services/*.py")


def test_registered_probes_expose_focused_commands() -> None:
    replaying_probe_ids = {
        "benchmark-evaluation-report-running-aggregates",
        "benchmark-export-run-scan-single-pass",
        "benchmark-store-matrix-streaming",
        "closure-audit-probe-source-short-circuit",
        "deterministic-rerank-query-context-reuse",
        "dev-up-mlx-metal-dist-info-scandir",
        "evaluation-job-id-high-water-mark",
        "evaluation-sample-probe-aggregation",
        "evaluation-store-compare-summary-csv-streaming",
        "evaluation-store-samples-csv-streaming",
        "job-registry-derived-model-single-pass",
        "package-macos-resolve-fallback-scandir",
        "pr-scoped-performance-scope-matcher",
        "training-dataset-token-percentiles-single-sort",
        "maintenance-bench-report-readback",
        "swift-cli-json-envelope-encoding",
        "upload-receipt-published-files-scandir",
        "download-pipeline-directory-size-single-stat",
        "worker-registry-resident-bytes-accumulator",
        "pr-scoped-performance-report-results-scandir",
    }
    for probe in load_probe_registry(REGISTRY_PATH):
        assert probe.test_command
        assert probe.coverage_command
        assert probe.coverage_replays_tests is (probe.probe_id in replaying_probe_ids)
        if probe.probe_impl == "command_json":
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


def test_single_pass_sample_iterable_rejects_repeated_iteration() -> None:
    samples = _build_large_training_dataset_samples()[:2]
    iterable = _single_pass_sample_iterable(samples)

    assert list(iterable) == samples
    with pytest.raises(RuntimeError, match="consumed more than once"):
        list(iterable)


def test_probe_training_dataset_token_percentiles_reports_quality_and_tracing_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample_rows = _build_large_training_dataset_quality_samples()[:4]
    calls = 0

    class FakeTrainingDatasetModule:
        @staticmethod
        def _build_quality_and_token_stats(samples: object, format_name: str) -> tuple[dict[str, float], dict[str, float]]:
            nonlocal calls
            calls += 1
            assert format_name == "prompt_completion"
            assert samples is sample_rows
            return (
                {
                    "duplicate_count": 2.0,
                    "dirty_count": 1.0,
                },
                {
                    "sample_count": float(len(sample_rows)),
                },
            )

    class FakeTraceMalloc:
        def __init__(self) -> None:
            self.started = 0
            self.stopped = 0

        def start(self) -> None:
            self.started += 1

        def get_traced_memory(self) -> tuple[int, int]:
            return (111, 222)

        def stop(self) -> None:
            self.stopped += 1

    fake_tracemalloc = FakeTraceMalloc()

    monkeypatch.setattr(
        pr_scoped_performance_module,
        "_load_repo_module",
        lambda path, *, unique_name: FakeTrainingDatasetModule(),
    )
    monkeypatch.setattr(
        pr_scoped_performance_module,
        "_build_large_training_dataset_quality_samples",
        lambda: sample_rows,
    )
    monkeypatch.setattr(pr_scoped_performance_module, "tracemalloc", fake_tracemalloc)

    metrics = _probe_training_dataset_token_percentiles(REPO_ROOT)

    assert calls == 3
    assert fake_tracemalloc.started == 3
    assert fake_tracemalloc.stopped == 3
    assert metrics["sample_count"] == float(len(sample_rows))
    assert metrics["duplicate_count"] == 2.0
    assert metrics["dirty_count"] == 1.0
    assert metrics["peak_bytes_mean"] == 222.0
    assert metrics["elapsed_ms_mean"] >= 0


def test_probe_smokes_return_metrics_against_current_repo() -> None:
    benchmark_metrics = _probe_benchmark_evaluation_report(REPO_ROOT)
    benchmark_export_metrics = _probe_benchmark_export_run_scan(REPO_ROOT)
    closure_metrics = _probe_closure_audit(REPO_ROOT)
    rerank_metrics = _probe_deterministic_rerank_query_context_reuse(REPO_ROOT)
    evaluation_job_id_metrics = _probe_evaluation_job_id(REPO_ROOT)
    evaluation_sample_probe_metrics = _probe_evaluation_sample_probe_aggregation(REPO_ROOT)
    evaluation_store_compare_summary_metrics = _probe_evaluation_store_compare_summary_csv_streaming(REPO_ROOT)
    evaluation_store_metrics = _probe_evaluation_store_samples_csv_streaming(REPO_ROOT)
    scope_matcher_metrics = _probe_pr_scoped_scope_matcher(REPO_ROOT)
    training_dataset_metrics = _probe_training_dataset_token_percentiles(REPO_ROOT)

    assert benchmark_metrics["elapsed_ms_mean"] > 0
    assert benchmark_metrics["peak_bytes_mean"] > 0
    assert benchmark_metrics["row_count"] > 0
    assert benchmark_export_metrics["elapsed_ms_mean"] > 0
    assert benchmark_export_metrics["per_run_ms_mean"] > 0
    assert benchmark_export_metrics["run_directory_count"] == 240.0
    assert benchmark_export_metrics["result_file_count"] == 720.0
    assert closure_metrics["elapsed_ms_mean"] > 0
    assert closure_metrics["probe_file_reads_mean"] > 0
    assert closure_metrics["finding_count"] > 0
    assert rerank_metrics["elapsed_ms_mean"] > 0
    assert rerank_metrics["query_context_builds_mean"] == 1.0
    assert rerank_metrics["document_count"] == 2048.0
    assert rerank_metrics["iteration_count"] == 8.0
    assert rerank_metrics["tokenize_calls_mean"] == 2049.0
    assert evaluation_job_id_metrics["elapsed_ms_mean"] > 0
    assert evaluation_job_id_metrics["per_call_ms_mean"] > 0
    assert evaluation_job_id_metrics["allocation_count"] == 200.0
    assert evaluation_job_id_metrics["first_job_id_numeric"] == 2001.0
    assert evaluation_job_id_metrics["last_job_id_numeric"] == 2200.0
    assert evaluation_sample_probe_metrics["elapsed_ms_mean"] > 0
    assert evaluation_sample_probe_metrics["per_call_ms_mean"] > 0
    assert evaluation_sample_probe_metrics["sample_count"] == 20000.0
    assert evaluation_sample_probe_metrics["metric_count"] == 7.0
    assert evaluation_store_compare_summary_metrics["elapsed_ms_mean"] > 0
    assert evaluation_store_compare_summary_metrics["peak_bytes_mean"] > 0
    assert evaluation_store_compare_summary_metrics["summary_count"] == 10000.0
    assert evaluation_store_compare_summary_metrics["csv_line_count"] == 10001.0
    assert evaluation_store_compare_summary_metrics["csv_bytes"] > 0
    assert evaluation_store_metrics["elapsed_ms_mean"] > 0
    assert evaluation_store_metrics["peak_bytes_mean"] > 0
    assert evaluation_store_metrics["sample_count"] == 10000.0
    assert evaluation_store_metrics["csv_line_count"] == 10001.0
    assert scope_matcher_metrics["build_scope_report_ms_mean"] > 0
    assert scope_matcher_metrics["changed_file_count"] == float(len(_build_large_scope_probe_changed_files()))
    assert scope_matcher_metrics["selected_probe_count_mean"] == 4.0
    assert scope_matcher_metrics["force_all_selected_mean"] == 0.0
    assert training_dataset_metrics["elapsed_ms_mean"] > 0
    assert training_dataset_metrics["peak_bytes_mean"] > 0
    assert training_dataset_metrics["sample_count"] == 20000.0
    assert training_dataset_metrics["duplicate_count"] > 0
    assert training_dataset_metrics["dirty_count"] > 0


def test_probe_evaluation_store_compare_summary_csv_streaming_targets_direct_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_command: list[str] = []

    class FakeCompletedProcess:
        def __init__(self) -> None:
            self.stdout = json.dumps(
                {
                    "elapsed_ms_mean": 1.25,
                    "peak_bytes_mean": 2048.0,
                    "summary_count": 10000.0,
                    "csv_line_count": 10001.0,
                    "csv_bytes": 4096.0,
                },
                sort_keys=True,
            )

    def fake_run(command: list[str], **kwargs: object) -> FakeCompletedProcess:
        del kwargs
        captured_command.extend(command)
        return FakeCompletedProcess()

    monkeypatch.setattr(pr_scoped_performance_module.subprocess, "run", fake_run)

    metrics = _probe_evaluation_store_compare_summary_csv_streaming(REPO_ROOT)

    assert metrics["csv_bytes"] == 4096.0
    assert captured_command[:6] == [
        "uv",
        "run",
        "--project",
        str(REPO_ROOT / "services/mlx-worker-python"),
        "python3",
        "-c",
    ]
    probe_script = captured_command[6]
    assert "writer(summary_csv_path, job=job, summaries=summaries)" in probe_script
    assert "writer = getattr(store, '_write_compare_summary_csv', None)" in probe_script
    assert "store._compare_summary_csv(job=job, summaries=summaries)" in probe_script
    assert "persist_compare_result(" not in probe_script


def test_dispatch_probe_impl_supports_deterministic_rerank_probe() -> None:
    probe = ProbeDefinition(
        probe_id="deterministic-rerank-query-context-reuse",
        name="Deterministic rerank query-context reuse",
        runner="ubuntu-latest",
        watch_globs=("services/mlx-worker-python/worker/runtime/deterministic_rerank_runtime.py",),
        test_command="true",
        coverage_command="true",
        probe_impl="deterministic_rerank_query_context_reuse",
        probe_command='python3 -c "{}"',
        metrics=(MetricDefinition(key="elapsed_ms_mean", unit="ms", direction="lower_is_better"),),
    )

    metrics = _dispatch_probe_impl(probe=probe, repo_root=REPO_ROOT)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["query_context_builds_mean"] == 1.0
    assert metrics["document_count"] == 2048.0
    assert metrics["iteration_count"] == 8.0
    assert metrics["tokenize_calls_mean"] == 2049.0


def test_dispatch_probe_impl_supports_benchmark_export_probe() -> None:
    probe = ProbeDefinition(
        probe_id="benchmark-export-run-scan-single-pass",
        name="Benchmark export run-scan single pass",
        runner="ubuntu-latest",
        watch_globs=("services/mlx-worker-python/worker/productization/benchmark_export.py",),
        test_command="true",
        coverage_command="true",
        probe_impl="benchmark_export_run_scan",
        probe_command='python3 -c "{}"',
        metrics=(MetricDefinition(key="elapsed_ms_mean", unit="ms", direction="lower_is_better"),),
    )

    metrics = _dispatch_probe_impl(probe=probe, repo_root=REPO_ROOT)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["per_run_ms_mean"] > 0
    assert metrics["run_directory_count"] == 240.0
    assert metrics["result_file_count"] == 720.0


def test_probe_benchmark_export_run_scan_rejects_unexpected_job_count(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeBenchmarkExportModule:
        @staticmethod
        def collect_benchmark_artifacts(path: Path) -> dict[str, object]:
            del path
            return {"benchmark_jobs": [], "benchmark_results": [object()] * 720}

    monkeypatch.setattr(pr_scoped_performance_module, "_load_repo_module", lambda path, unique_name: FakeBenchmarkExportModule)

    with pytest.raises(ValueError, match="unexpected benchmark job count"):
        _probe_benchmark_export_run_scan(REPO_ROOT)


def test_probe_benchmark_export_run_scan_rejects_unexpected_result_count(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeBenchmarkExportModule:
        @staticmethod
        def collect_benchmark_artifacts(path: Path) -> dict[str, object]:
            del path
            return {"benchmark_jobs": [object()] * 240, "benchmark_results": []}

    monkeypatch.setattr(pr_scoped_performance_module, "_load_repo_module", lambda path, unique_name: FakeBenchmarkExportModule)

    with pytest.raises(ValueError, match="unexpected benchmark result count"):
        _probe_benchmark_export_run_scan(REPO_ROOT)


def test_worker_registry_probe_script_emits_metrics(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(REPO_ROOT / "scripts/worker_registry_resident_probe.py"), run_name="__main__")

    assert excinfo.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["elapsed_ms_mean"] > 0
    assert payload["preloaded_model_count"] == 2000.0
    assert payload["loop_count"] == 250.0
    assert payload["request_count"] == 3000.0
    assert payload["request_stats_elapsed_ms_mean"] > 0
    assert payload["resident_bytes_mean"] > 0
    assert payload["sample_count"] == 3.0


def test_job_registry_probe_script_emits_metrics(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(REPO_ROOT / "scripts/job_registry_derived_model_probe.py"), run_name="__main__")

    assert excinfo.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["active_manifest_elapsed_ms_mean"] > 0
    assert payload["resolve_target_elapsed_ms_mean"] > 0
    assert payload["active_manifest_count"] == 960.0
    assert payload["removed_count"] == 240.0
    assert payload["sample_count"] == 6.0


def test_benchmark_store_probe_script_emits_metrics(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(REPO_ROOT / "scripts/benchmark_store_probe.py"), run_name="__main__")

    assert excinfo.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["elapsed_ms_mean"] > 0
    assert payload["peak_bytes_mean"] > 0
    assert payload["summary_row_count"] == 750.0
    assert payload["request_row_count"] == 6000.0
    assert payload["request_csv_line_count"] == 6001.0
    assert payload["sample_count"] == 3.0


def test_upload_receipt_probe_script_emits_metrics(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(REPO_ROOT / "scripts/upload_receipt_published_files_probe.py"), run_name="__main__")

    assert excinfo.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["elapsed_ms_mean"] > 0
    assert payload["directory_count"] == 180.0
    assert payload["files_per_directory"] == 40.0
    assert payload["published_file_count"] == 7201.0
    assert payload["sample_count"] == 5.0


def test_dispatch_probe_impl_supports_upload_receipt_published_files_probe() -> None:
    probe = ProbeDefinition(
        probe_id="upload-receipt-published-files-scandir",
        name="Upload receipt published-files scandir",
        runner="ubuntu-latest",
        watch_globs=("services/mlx-worker-python/worker/model_ops/upload_receipt_pipeline.py",),
        test_command="true",
        coverage_command="true",
        probe_impl="upload_receipt_published_files",
        probe_command="python3 scripts/upload_receipt_published_files_probe.py",
        metrics=(MetricDefinition(key="elapsed_ms_mean", unit="ms", direction="lower_is_better"),),
    )

    metrics = _dispatch_probe_impl(probe=probe, repo_root=REPO_ROOT)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["directory_count"] == 180.0
    assert metrics["files_per_directory"] == 40.0
    assert metrics["published_file_count"] == 7201.0
    assert metrics["sample_count"] == 5.0


def test_dispatch_probe_impl_supports_pr_scoped_scope_matcher_probe() -> None:
    probe = ProbeDefinition(
        probe_id="pr-scoped-performance-scope-matcher",
        name="PR-scoped performance scope matcher",
        runner="ubuntu-latest",
        watch_globs=("services/mlx-worker-python/worker/productization/pr_scoped_performance.py",),
        test_command="true",
        coverage_command="true",
        probe_impl="pr_scoped_scope_matcher",
        probe_command='python3 -c "{}"',
        metrics=(MetricDefinition(key="build_scope_report_ms_mean", unit="ms", direction="lower_is_better"),),
    )

    metrics = _dispatch_probe_impl(probe=probe, repo_root=REPO_ROOT)

    assert metrics["build_scope_report_ms_mean"] > 0
    assert metrics["changed_file_count"] == float(len(_build_large_scope_probe_changed_files()))
    assert metrics["selected_probe_count_mean"] == 4.0
    assert metrics["force_all_selected_mean"] == 0.0


def test_upload_receipt_probe_loader_stubs_external_imports(tmp_path: Path) -> None:
    module_path = tmp_path / "services/mlx-worker-python/worker/model_ops/upload_receipt_pipeline.py"
    module_path.parent.mkdir(parents=True)
    module_path.write_text(
        "from __future__ import annotations\n"
        "from packages.protocol.python.worker.v1 import maintenance_pb2\n"
        "from worker.model_ops.errors import ModelOperationError\n"
        "class UploadReceiptPipeline:\n"
        "    @staticmethod\n"
        "    def _collect_published_file_list(source_dir):\n"
        "        return [maintenance_pb2.__name__, ModelOperationError.__name__]\n",
        encoding="utf-8",
    )

    module_names = (
        "packages.protocol.python.worker.v1.maintenance_pb2",
        "worker.model_ops.errors",
    )
    previous_modules = {name: sys.modules.get(name) for name in module_names}

    module = _load_upload_receipt_pipeline_module(module_path)

    assert module.UploadReceiptPipeline._collect_published_file_list(tmp_path) == [
        "packages.protocol.python.worker.v1.maintenance_pb2",
        "ModelOperationError",
    ]
    for name, previous in previous_modules.items():
        assert sys.modules.get(name) is previous


def test_dispatch_probe_impl_supports_evaluation_job_id_probe() -> None:
    probe = ProbeDefinition(
        probe_id="evaluation-job-id-high-water-mark",
        name="Evaluation job-id high-water mark",
        runner="ubuntu-latest",
        watch_globs=("services/mlx-worker-python/worker/engine/evaluation_core.py",),
        test_command="true",
        coverage_command="true",
        probe_impl="evaluation_job_id",
        probe_command='python3 -c "{}"',
        metrics=(MetricDefinition(key="elapsed_ms_mean", unit="ms", direction="lower_is_better"),),
    )

    metrics = _dispatch_probe_impl(probe=probe, repo_root=REPO_ROOT)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["per_call_ms_mean"] > 0
    assert metrics["allocation_count"] == 200.0


def test_dispatch_probe_impl_supports_evaluation_store_compare_summary_probe() -> None:
    probe = ProbeDefinition(
        probe_id="evaluation-store-compare-summary-csv-streaming",
        name="Evaluation store compare summary CSV streaming",
        runner="ubuntu-latest",
        watch_globs=("services/mlx-worker-python/worker/productization/evaluation_store.py",),
        test_command="true",
        coverage_command="true",
        probe_impl="evaluation_store_compare_summary_csv_streaming",
        probe_command='python3 -c "{}"',
        metrics=(MetricDefinition(key="elapsed_ms_mean", unit="ms", direction="lower_is_better"),),
    )

    metrics = _dispatch_probe_impl(probe=probe, repo_root=REPO_ROOT)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["summary_count"] == 10000.0
    assert metrics["csv_line_count"] == 10001.0



def test_dispatch_probe_impl_supports_evaluation_store_probe() -> None:
    probe = ProbeDefinition(
        probe_id="evaluation-store-samples-csv-streaming",
        name="Evaluation store samples CSV streaming",
        runner="ubuntu-latest",
        watch_globs=("services/mlx-worker-python/worker/productization/evaluation_store.py",),
        test_command="true",
        coverage_command="true",
        probe_impl="evaluation_store_samples_csv_streaming",
        probe_command='python3 -c "{}"',
        metrics=(MetricDefinition(key="elapsed_ms_mean", unit="ms", direction="lower_is_better"),),
    )

    metrics = _dispatch_probe_impl(probe=probe, repo_root=REPO_ROOT)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["sample_count"] == 10000.0
    assert metrics["csv_line_count"] == 10001.0


def test_dispatch_probe_impl_supports_evaluation_sample_probe_aggregation_probe() -> None:
    probe = ProbeDefinition(
        probe_id="evaluation-sample-probe-aggregation",
        name="Evaluation sample probe aggregation",
        runner="ubuntu-latest",
        watch_globs=("services/mlx-worker-python/worker/engine/evaluation_core.py",),
        test_command="true",
        coverage_command="true",
        probe_impl="evaluation_sample_probe_aggregation",
        probe_command='python3 -c "{}"',
        metrics=(MetricDefinition(key="elapsed_ms_mean", unit="ms", direction="lower_is_better"),),
    )

    metrics = _dispatch_probe_impl(probe=probe, repo_root=REPO_ROOT)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["per_call_ms_mean"] > 0
    assert metrics["metric_count"] == 7.0


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


def test_run_head_verification_skips_standalone_test_when_coverage_replays_tests(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    commands: list[str] = []

    def fake_run_command(command: str, *, cwd: Path) -> dict[str, object]:
        commands.append(command)
        assert cwd == tmp_path
        return {
            "command": command,
            "ok": True,
            "returncode": 0,
            "stdout": "TOTAL 1 0 100%\n",
            "stderr": "",
            "coverage_pct": 100.0,
        }

    monkeypatch.setattr(pr_scoped_performance_module, "_run_command", fake_run_command)
    probe = ProbeDefinition(
        probe_id="demo",
        name="Demo",
        runner="ubuntu-latest",
        watch_globs=("demo.py",),
        test_command="pytest -q demo",
        coverage_command="coverage run -m pytest -q demo",
        probe_impl="benchmark_evaluation_report",
        probe_command="",
        metrics=(MetricDefinition(key="elapsed_ms_mean", unit="ms", direction="lower_is_better"),),
        coverage_replays_tests=True,
    )

    result = _run_head_verification(probe=probe, repo_root=tmp_path)

    assert commands == ["coverage run -m pytest -q demo"]
    assert result["test"]["ok"] is True
    assert "Skipped standalone test command" in result["test"]["stdout"]
    assert result["coverage"]["coverage_pct"] == 100.0


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


def test_report_results_loader_uses_scandir_and_binary_json_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "b.json").write_text(json.dumps({"probe": {"id": "b"}}), encoding="utf-8")
    (results_dir / "a.json").write_text(json.dumps({"probe": {"id": "a"}}), encoding="utf-8")
    (results_dir / "ignored.txt").write_text("ignored", encoding="utf-8")

    def fail_glob(self: Path, pattern: str):
        raise AssertionError("_load_results should use os.scandir instead of Path.glob")

    def fail_json_load(*args: object, **kwargs: object):  # pragma: no cover - sentinel
        raise AssertionError("_load_results should parse binary file contents with json.loads")

    monkeypatch.setattr(Path, "glob", fail_glob)
    monkeypatch.setattr(json, "load", fail_json_load)

    report_script = runpy.run_path(str(REPO_ROOT / "scripts/pr_scoped_performance_report.py"))
    loaded = report_script["_load_results"](results_dir)

    assert [payload["probe"]["id"] for payload in loaded] == ["a", "b"]


def test_performance_report_script_load_results_handles_missing_directory() -> None:
    report_script = runpy.run_path(str(REPO_ROOT / "scripts/pr_scoped_performance_report.py"))

    assert report_script["_load_results"](REPO_ROOT / "missing-results-dir") == []



def test_performance_report_script_json_output_and_invalid_scope(
    tmp_path: Path,
    benchmark_scope: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    scope_path = tmp_path / "scope.json"
    scope_path.write_text(json.dumps(benchmark_scope), encoding="utf-8")
    results_dir = tmp_path / "results"
    results_dir.mkdir()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pr_scoped_performance_report.py",
            "--scope",
            str(scope_path),
            "--results-dir",
            str(results_dir),
            "--format",
            "json",
        ],
    )
    report_script = runpy.run_path(str(REPO_ROOT / "scripts/pr_scoped_performance_report.py"))

    assert report_script["main"]() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["selected_probe_count"] == benchmark_scope["selected_count"]

    invalid_scope_path = tmp_path / "invalid-scope.json"
    invalid_scope_path.write_text("[]\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pr_scoped_performance_report.py",
            "--scope",
            str(invalid_scope_path),
            "--results-dir",
            str(results_dir),
        ],
    )

    with pytest.raises(ValueError, match="scope payload must be a JSON object"):
        report_script["main"]()



def test_pr_scoped_performance_report_script_exits_zero_as_main_module(
    tmp_path: Path,
    benchmark_scope: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope_path = tmp_path / "scope.json"
    scope_path.write_text(json.dumps(benchmark_scope), encoding="utf-8")
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pr_scoped_performance_report.py",
            "--scope",
            str(scope_path),
            "--results-dir",
            str(results_dir),
            "--format",
            "json",
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(REPO_ROOT / "scripts/pr_scoped_performance_report.py"), run_name="__main__")

    assert excinfo.value.code == 0



def test_performance_report_results_probe_script_emits_metrics(capsys: pytest.CaptureFixture[str]) -> None:
    probe_script = runpy.run_path(str(REPO_ROOT / "scripts/pr_scoped_performance_report_results_probe.py"))

    assert probe_script["main"]() == 0

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["file_count"] == 2000.0
    assert metrics["result_count"] == 2000.0
    assert metrics["sample_count"] == 5.0
    assert metrics["elapsed_ms_mean"] > 0.0


def test_package_macos_resolve_probe_script_emits_metrics(capsys: pytest.CaptureFixture[str]) -> None:
    probe_script = runpy.run_path(str(REPO_ROOT / "scripts/package_macos_resolve_probe.py"))

    assert probe_script["main"]() == 0

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 9.0
    assert metrics["triple_count"] == 1500.0
    assert metrics["elapsed_ms_mean"] >= 0.0


def test_package_macos_resolve_probe_rejects_unexpected_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    probe_script = runpy.run_path(str(REPO_ROOT / "scripts/package_macos_resolve_probe.py"))

    class WrongModule:
        @staticmethod
        def resolve_built_binary(repo_root: Path) -> Path:
            return repo_root / "apps/macos-menubar/.build/arch-0001/debug/melix-menubar"

    monkeypatch.setitem(
        probe_script["main"].__globals__,
        "_load_packaging_module",
        lambda repo_root: WrongModule,
    )

    with pytest.raises(AssertionError, match="expected .* got"):
        probe_script["main"]()


def test_report_script_writes_sticky_comment_artifact_for_terminal_output(
    tmp_path: Path,
    benchmark_scope: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
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
    scope_path = tmp_path / "scope.json"
    scope_path.write_text(json.dumps(benchmark_scope), encoding="utf-8")
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "probe.json").write_text(json.dumps(result), encoding="utf-8")
    report_dir = tmp_path / "report"
    expected_markdown = render_markdown_report(
        build_performance_report(scope=benchmark_scope, probe_results=[result])
    )
    expected_sticky = build_sticky_comment_body(expected_markdown)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pr_scoped_performance_report.py",
            "--scope",
            str(scope_path),
            "--results-dir",
            str(results_dir),
            "--output-dir",
            str(report_dir),
            "--format",
            "terminal",
            "--sticky-comment",
        ],
    )
    report_script = runpy.run_path(str(REPO_ROOT / "scripts/pr_scoped_performance_report.py"))

    assert report_script["main"]() == 0

    captured = capsys.readouterr().out
    assert captured.startswith("Melix PR Scoped Performance Report\n")
    assert (report_dir / "report.md").read_text(encoding="utf-8") == expected_markdown
    assert (report_dir / "pr-comment.md").read_text(encoding="utf-8") == expected_sticky



def test_report_script_preserves_exact_sticky_comment_body_on_markdown_stdout(
    tmp_path: Path,
    benchmark_scope: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
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
    scope_path = tmp_path / "scope.json"
    scope_path.write_text(json.dumps(benchmark_scope), encoding="utf-8")
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "probe.json").write_text(json.dumps(result), encoding="utf-8")
    report_dir = tmp_path / "report"
    expected_markdown = render_markdown_report(
        build_performance_report(scope=benchmark_scope, probe_results=[result])
    )
    expected_sticky = build_sticky_comment_body(expected_markdown)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pr_scoped_performance_report.py",
            "--scope",
            str(scope_path),
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

    assert capsys.readouterr().out == expected_sticky
    assert (report_dir / "report.md").read_text(encoding="utf-8") == expected_markdown
    assert (report_dir / "pr-comment.md").read_text(encoding="utf-8") == expected_sticky



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
