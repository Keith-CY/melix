from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import time
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
    _summarize_command,
    _build_probe_report_row,
    _build_probe_details,
    _closure_index_text,
    _compiled_glob_pattern,
    _dict_list,
    _dispatch_probe_impl,
    _float_or_none,
    _format_delta,
    _format_value,
    _glob_literal_prefix,
    _is_relative_to,
    _load_upload_receipt_pipeline_module,
    _load_repo_module,
    _markdown_cell,
    _matches_any_glob,
    _match_probe_indexes,
    _parse_coverage_percent,
    _probe_benchmark_evaluation_report,
    _probe_benchmark_export_run_scan,
    _probe_benchmark_queue_cache,
    _probe_closure_audit,
    _probe_deterministic_rerank_query_context_reuse,
    _probe_evaluation_job_id,
    _probe_evaluation_sample_probe_aggregation,
    _probe_evaluation_store_compare_summary_csv_streaming,
    _probe_evaluation_store_samples_csv_streaming,
    _probe_pr_scoped_scope_matcher,
    _probe_training_dataset_token_percentiles,
    _probe_model_ops_bundle_artifact_bytes,
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


def test_scope_report_selects_hub_catalog_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/model_ops/hub_catalog.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "hub-catalog-tag-normalization-single-pass"


def test_scope_report_selects_stream_assembler_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/runtime/stream_assembler.py"],
    )

    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert scope["selected_count"] == 2
    assert probe_ids == {
        "stream-assembler-parser-mode-cache",
        "stream-assembler-structural-prefix-cache",
    }


def test_scope_report_selects_runtime_utils_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/runtime/runtime_utils.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "runtime-utils-kwarg-signature-cache"


def test_scope_report_selects_dataset_registry_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/dataset_registry/catalog.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "dataset-registry-limited-read-streaming"


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


def test_scope_report_selects_startup_signals_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/productization/startup_signals.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "startup-signals-lazy-worker-log-excerpts"


def test_scope_report_selects_real_model_support_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["scripts/real_model_support.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "real-model-support-hf-cache-latest-snapshot"


def test_scope_report_selects_evaluation_probes() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/engine/evaluation_core.py"],
    )

    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert scope["selected_count"] == 4
    assert probe_ids == {
        "evaluation-dialogue-diagnostics-top-k",
        "evaluation-job-id-high-water-mark",
        "evaluation-latency-percentile-vector-reuse",
        "evaluation-sample-probe-aggregation",
    }


def test_scope_report_selects_code_eval_stdio_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/engine/code_eval_runner.py"],
    )

    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert scope["selected_count"] == 2
    assert probe_ids == {
        "code-eval-code-block-last-match-streaming",
        "code-eval-stdio-tail-single-stat",
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


def test_scope_report_selects_evaluation_final_result_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/productization/evaluation_final_result.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "evaluation-final-result-materialization-streaming"


def test_dispatch_probe_impl_supports_evaluation_final_result_probe() -> None:
    probe = next(
        probe
        for probe in load_probe_registry(REGISTRY_PATH)
        if probe.probe_id == "evaluation-final-result-materialization-streaming"
    )

    metrics = _dispatch_probe_impl(probe=probe, repo_root=REPO_ROOT)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["sample_count"] == 15000.0



def test_scope_report_selects_multimodal_fast_path_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/runtime/multimodal_fast_paths.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "multimodal-fast-path-signature-top-level-key-cache"


def test_scope_report_selects_worker_registry_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/registry.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "worker-registry-resident-bytes-accumulator"


def test_scope_report_selects_lora_reward_summary_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=[
            "services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py"
        ],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "lora-reward-summary-candidate-minmax"


def test_scope_report_selects_statistical_evidence_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/productization/statistical_evidence.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "statistical-evidence-bootstrap-single-sort"


def test_scope_report_selects_pr_scoped_scope_script_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["scripts/pr_scoped_performance_scope.py"],
    )

    selected_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert scope["force_all"] is True
    assert "pr-scoped-performance-scope-json-read-bytes" in selected_ids


def test_scope_report_selects_changed_scope_coverage_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["scripts/changed_scope_coverage.py"],
    )

    selected_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert "changed-scope-coverage-empty-path-short-circuit" in selected_ids


def test_scope_report_selects_changed_scope_coverage_parser_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["scripts/changed_scope_coverage.py"],
    )

    selected_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert scope["force_all"] is False
    assert "changed-scope-coverage-diff-parser" in selected_ids


def test_scope_report_selects_job_registry_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/model_ops/job_registry.py"],
    )

    assert scope["selected_count"] == 2
    assert [probe["id"] for probe in scope["selected_probes"]] == [
        "job-registry-derived-model-single-pass",
        "job-registry-restore-sort-elision",
    ]


def test_scope_report_selects_mlx_lm_runner_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "mlx-lm-structured-result-tail-parse"


def test_scope_report_selects_mlx_vlm_runtime_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/runtime/mlx_vlm_runtime.py"],
    )

    assert scope["selected_count"] == 2
    assert [probe["id"] for probe in scope["selected_probes"]] == [
        "mlx-vlm-family-config-cache",
        "mlx-vlm-gemma4-weight-presence-single-pass",
    ]


def test_scope_report_selects_model_registry_catalog_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/model_registry/catalog.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "model-registry-plain-local-manifest-stat-elision"


def test_scope_report_selects_deterministic_rerank_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/runtime/deterministic_rerank_runtime.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "deterministic-rerank-query-context-reuse"


def test_scope_report_selects_embedding_project_digest_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/runtime/embedding_backends.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "deterministic-embedding-project-digest-allocation"


def test_deterministic_embedding_project_digest_probe_script_smoke(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(
            str(REPO_ROOT / "scripts/deterministic_embedding_project_digest_probe.py"),
            run_name="__main__",
        )
    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["sample_count"] == 3.0
    assert metrics["vector_count"] == 500.0
    assert metrics["dimensions"] == 4096.0


def test_scope_report_selects_rerank_core_top_k_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/engine/rerank_core.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "rerank-core-top-k-heap-selection"


def test_scope_report_selects_deterministic_embedding_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/runtime/deterministic_embedding_runtime.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "deterministic-embedding-duplicate-input-cache"


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


def test_scope_report_selects_benchmark_queue_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/productization/benchmark_queue.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "benchmark-queue-decoded-record-cache"


def test_scope_report_selects_model_ops_bundle_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/model_ops/conversion_pipeline.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "model-ops-bundle-artifact-byte-accounting"


def test_scope_report_selects_phase8_metrics_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["scripts/phase8_metrics_report.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "phase8-metrics-closure-audit-reuse"


def test_scope_report_selects_bench_report_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/engine/maintenance_core.py"],
    )

    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert "maintenance-bench-report-readback" in probe_ids


def test_scope_report_selects_maintenance_percentile_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/engine/maintenance_core.py"],
    )

    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert "maintenance-percentile-vector-reuse" in probe_ids


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


def test_scope_report_selects_registry_cache_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/productization/pr_scoped_performance.py"],
    )

    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert "pr-scoped-performance-registry-cache" in probe_ids


def test_scope_report_force_selects_all_on_infra_change() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["infra/perf/pr_scoped_probes.json"],
    )

    assert scope["force_all"] is True
    assert scope["selected_count"] == len(load_probe_registry(REGISTRY_PATH))
    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert "pr-scoped-performance-scope-matcher" in probe_ids


def test_scope_report_exact_force_all_skips_wildcard_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_wildcard_scan(changed_paths: set[str]) -> bool:  # pragma: no cover - sentinel
        raise AssertionError("exact force-all matches should not scan wildcard matchers")

    monkeypatch.setattr(
        pr_scoped_performance_module,
        "_changed_paths_match_force_all_wildcards",
        fail_wildcard_scan,
    )

    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["infra/perf/pr_scoped_probes.json", "README.md"],
    )

    assert scope["force_all"] is True
    assert scope["selected_count"] == len(load_probe_registry(REGISTRY_PATH))


def test_scope_report_force_selects_all_on_pr_scope_script_change() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["scripts/pr_scoped_performance_report.py"],
    )

    assert scope["force_all"] is True
    assert scope["selected_count"] == len(load_probe_registry(REGISTRY_PATH))


def test_changed_paths_force_all_wildcards_handles_empty_matchers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pr_scoped_performance_module, "_force_all_wildcard_matchers", lambda: ())

    assert pr_scoped_performance_module._changed_paths_match_force_all_wildcards({"README.md"}) is False


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
        "evaluation-latency-percentile-vector-reuse",
        "download-pipeline-directory-size-single-stat",
    ]
    assert scope["selected_count"] == 5


def test_match_probe_indexes_deduplicates_repeated_watch_globs() -> None:
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
    matched = _match_probe_indexes(changed_paths=("shared.py", "services/b.py", "unmatched.py"), probes=probes)

    assert matched == {0, 1, 2}


def test_match_probe_indexes_exact_only_intersects_changed_paths() -> None:
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
            watch_globs=("services/b.py",),
            test_command="true",
            coverage_command="true",
            probe_impl="benchmark_evaluation_report",
            probe_command="",
            metrics=(MetricDefinition(key="elapsed_ms_mean", unit="ms", direction="lower_is_better"),),
        ),
    )

    matched = _match_probe_indexes(
        changed_paths={"shared.py", "docs/readme.md", "services/b.py"},
        probes=probes,
    )

    assert matched == {0, 1}


def test_match_probe_indexes_skips_prefix_misses_before_regex(monkeypatch: pytest.MonkeyPatch) -> None:
    probes = (
        ProbeDefinition(
            probe_id="alpha",
            name="Alpha",
            runner="ubuntu-latest",
            watch_globs=("services/*.py",),
            test_command="true",
            coverage_command="true",
            probe_impl="benchmark_evaluation_report",
            probe_command="",
            metrics=(MetricDefinition(key="elapsed_ms_mean", unit="ms", direction="lower_is_better"),),
        ),
    )
    match_calls: list[str] = []

    class FailingPattern:
        def match(self, path: str) -> None:  # pragma: no cover - sentinel
            match_calls.append(path)
            raise AssertionError("prefix misses should not invoke regex matching")

    monkeypatch.setattr(pr_scoped_performance_module, "_compiled_glob_pattern", lambda glob: FailingPattern())

    assert _match_probe_indexes(changed_paths=("docs/a.md", "README.md"), probes=probes) == set()
    assert match_calls == []


def test_compiled_glob_pattern_reuses_cached_regex(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _compiled_glob_pattern("services/*.py") is _compiled_glob_pattern("services/*.py")

    pr_scoped_performance_module._force_all_wildcard_matchers.cache_clear()
    compile_calls: list[str] = []
    original_compile = pr_scoped_performance_module._compiled_glob_pattern

    def tracked_compile(glob: str):
        compile_calls.append(glob)
        return original_compile(glob)

    monkeypatch.setattr(pr_scoped_performance_module, "_compiled_glob_pattern", tracked_compile)

    assert pr_scoped_performance_module._path_matches_force_all("scripts/pr_scoped_performance_run.py") is True
    assert pr_scoped_performance_module._path_matches_force_all("docs/plans/scope.md") is False
    assert compile_calls == ["scripts/pr_scoped_performance_*.py"]
    assert pr_scoped_performance_module._path_matches_force_all("scripts/pr_scoped_performance_report.py") is True
    assert compile_calls == ["scripts/pr_scoped_performance_*.py"]

    pr_scoped_performance_module._force_all_wildcard_matchers.cache_clear()


def test_hub_catalog_tag_normalization_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_HUB_CATALOG_TAG_PROBE_RECORDS", "3")
    monkeypatch.setenv("MELIX_HUB_CATALOG_TAG_PROBE_SAMPLES", "1")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(REPO_ROOT / "scripts/hub_catalog_tag_normalization_probe.py"), run_name="__main__")

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["record_count"] == 3.0
    assert metrics["sample_count"] == 1.0
    assert metrics["tag_normalization_calls_mean"] == 3.0
    assert metrics["elapsed_ms_mean"] >= 0
    assert metrics["peak_bytes_mean"] > 0


def test_statistical_evidence_bootstrap_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_STAT_EVIDENCE_SAMPLE_SIZE", "16")
    monkeypatch.setenv("MELIX_STAT_EVIDENCE_BOOTSTRAP_ITERATIONS", "8")
    monkeypatch.setenv("MELIX_STAT_EVIDENCE_PROBE_SAMPLES", "1")

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(
            str(REPO_ROOT / "scripts/statistical_evidence_bootstrap_probe.py"),
            run_name="__main__",
        )

    assert excinfo.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 1.0
    assert metrics["sample_size"] == 16.0
    assert metrics["bootstrap_iterations"] == 8.0
    assert metrics["sorted_calls_mean"] == 1.0
    assert metrics["elapsed_ms_mean"] >= 0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["lower_bound_mean"] <= metrics["upper_bound_mean"]


def test_multimodal_fast_path_signature_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_MULTIMODAL_SIGNATURE_PROBE_ITERATIONS", "3")
    monkeypatch.setenv("MELIX_MULTIMODAL_SIGNATURE_PROBE_SAMPLES", "1")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(REPO_ROOT / "scripts/multimodal_fast_path_signature_probe.py"), run_name="__main__")

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 1.0
    assert metrics["iterations_per_sample"] == 3.0
    assert metrics["signature_count"] == 3.0
    assert metrics["top_level_item_count"] == 4.0
    assert metrics["elapsed_ms_mean"] >= 0
    assert metrics["peak_bytes_mean"] > 0


def test_deterministic_embedding_duplicate_probe_script_emits_metrics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    runpy.run_path(
        str(REPO_ROOT / "scripts/deterministic_embedding_duplicate_probe.py"),
        run_name="__main__",
    )

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["input_count"] == 8192.0
    assert 0 < metrics["unique_input_count"] < metrics["input_count"]
    assert metrics["embed_text_calls_mean"] == metrics["unique_input_count"]
    assert metrics["elapsed_ms_mean"] >= 0
    assert metrics["checksum"] > 0


def test_stream_assembler_structural_prefix_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_STREAM_PREFIX_PROBE_ITERATIONS", "3")
    monkeypatch.setenv("MELIX_STREAM_PREFIX_PROBE_SAMPLES", "1")

    runpy.run_path(
        str(REPO_ROOT / "scripts/stream_assembler_structural_prefix_probe.py"),
        run_name="__main__",
    )

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 1.0
    assert metrics["iteration_count"] == 3.0
    assert metrics["held_suffix_hits"] == 3.0
    assert metrics["prefix_identity_hits"] == 3.0
    assert metrics["elapsed_ms_mean"] >= 0
    assert metrics["peak_bytes_mean"] > 0


def test_runtime_utils_kwarg_cache_probe_script_emits_metrics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(
            str(REPO_ROOT / "scripts/runtime_utils_kwarg_cache_probe.py"),
            run_name="__main__",
        )

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 5.0
    assert metrics["iterations_per_sample"] == 40000.0
    assert metrics["inspect_signature_calls_mean"] == 2.0
    assert metrics["elapsed_ms_mean"] >= 0


def test_dataset_registry_limit_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_DATASET_LIMIT_PROBE_GROUPS", "2")
    monkeypatch.setenv("MELIX_DATASET_LIMIT_PROBE_FILES_PER_GROUP", "3")
    monkeypatch.setenv("MELIX_DATASET_LIMIT_PROBE_LIMIT", "2")
    monkeypatch.setenv("MELIX_DATASET_LIMIT_PROBE_SAMPLES", "1")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(
            str(REPO_ROOT / "scripts/dataset_registry_limit_probe.py"),
            run_name="__main__",
        )

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 1.0
    assert metrics["synthetic_file_count"] == 6.0
    assert metrics["limit"] == 2.0
    assert metrics["dataset_files_yielded_mean"] == 4.0
    assert metrics["elapsed_ms_mean"] >= 0
    assert metrics["peak_bytes_mean"] > 0


def test_registered_probes_expose_focused_commands() -> None:
    replaying_probe_ids = {
        "dataset-registry-limited-read-streaming",
        "hub-catalog-tag-normalization-single-pass",
        "benchmark-evaluation-report-running-aggregates",
        "statistical-evidence-bootstrap-percentile-single-sort",
        "stream-assembler-parser-mode-cache",
        "benchmark-export-run-scan-single-pass",
        "benchmark-queue-decoded-record-cache",
        "benchmark-store-matrix-streaming",
        "changed-scope-coverage-empty-path-short-circuit",
        "changed-scope-coverage-diff-parser",
        "closure-audit-probe-source-short-circuit",
        "code-eval-code-block-last-match-streaming",
        "code-eval-stdio-tail-single-stat",
        "deterministic-embedding-duplicate-input-cache",
        "deterministic-embedding-project-digest-allocation",
        "deterministic-rerank-query-context-reuse",
        "rerank-core-top-k-heap-selection",
        "runtime-utils-kwarg-signature-cache",
        "dev-up-mlx-metal-dist-info-scandir",
        "evaluation-job-id-high-water-mark",
        "evaluation-dialogue-diagnostics-top-k",
        "evaluation-final-result-materialization-streaming",
        "evaluation-latency-percentile-vector-reuse",
        "evaluation-sample-probe-aggregation",
        "evaluation-store-compare-summary-csv-streaming",
        "evaluation-store-samples-csv-streaming",
        "job-registry-derived-model-single-pass",
        "job-registry-restore-sort-elision",
        "lora-reward-summary-candidate-minmax",
        "mlx-lm-structured-result-tail-parse",
        "mlx-vlm-family-config-cache",
        "mlx-vlm-gemma4-weight-presence-single-pass",
        "model-registry-plain-local-manifest-stat-elision",
        "multimodal-fast-path-signature-top-level-key-cache",
        "package-macos-resolve-fallback-scandir",
        "pr-scoped-performance-scope-json-read-bytes",
        "pr-scoped-performance-scope-matcher",
        "training-dataset-token-percentiles-single-sort",
        "maintenance-bench-report-readback",
        "maintenance-percentile-vector-reuse",
        "phase8-metrics-closure-audit-reuse",
        "pr-scoped-performance-registry-cache",
        "real-model-support-hf-cache-latest-snapshot",
        "stream-assembler-structural-prefix-cache",
        "swift-cli-json-envelope-encoding",
        "startup-signals-lazy-worker-log-excerpts",
        "upload-receipt-published-files-scandir",
        "download-pipeline-directory-size-single-stat",
        "worker-registry-resident-bytes-accumulator",
        "pr-scoped-performance-report-results-scandir",
        "model-ops-bundle-artifact-byte-accounting",
        "statistical-evidence-bootstrap-single-sort",
    }
    registry_probe = None
    maintenance_probe = None
    worker_registry_probe = None
    swift_probe = None
    for probe in load_probe_registry(REGISTRY_PATH):
        assert probe.test_command
        assert probe.coverage_command
        assert probe.probe_command
        assert "uv run --project services/mlx-worker-python bash -lc" not in probe.probe_command
        assert probe.coverage_replays_tests is (probe.probe_id in replaying_probe_ids)
        if probe.probe_id == "model-registry-plain-local-manifest-stat-elision":
            registry_probe = probe
        if probe.probe_id == "maintenance-percentile-vector-reuse":
            maintenance_probe = probe
        if probe.probe_id == "worker-registry-resident-bytes-accumulator":
            worker_registry_probe = probe
        if probe.probe_id == "swift-cli-json-envelope-encoding":
            swift_probe = probe

    assert worker_registry_probe is not None
    assert "test_worker_registry_reuses_sorted_handles_across_listing_calls" in worker_registry_probe.test_command
    assert "test_load_model_returns_handle_and_lists_model" in worker_registry_probe.test_command
    assert "test_worker_registry_reuses_sorted_handles_across_listing_calls" in worker_registry_probe.coverage_command
    assert "test_load_model_returns_handle_and_lists_model" in worker_registry_probe.coverage_command

    assert registry_probe is not None
    assert "test_registry_snapshot_reuses_hf_cache_config_payload" in registry_probe.test_command
    assert "test_raw_model_spec_loads_config_payload_when_not_supplied" in registry_probe.test_command
    assert "test_has_mlx_signal_falls_back_to_config_text_for_empty_supplied_payload" in registry_probe.test_command
    assert "test_has_mlx_signal_skips_config_text_fallback_for_nonempty_payload_without_mlx_signal" in registry_probe.test_command
    assert "test_metadata_payload_has_mlx_signal_does_not_request_sorted_json" in registry_probe.test_command
    assert "test_has_mlx_signal_config_payload_fast_path_does_not_request_sorted_json" in registry_probe.test_command
    assert "scripts/changed_scope_coverage.py" in registry_probe.watch_globs
    assert "test_registry_snapshot_reuses_hf_cache_config_payload" in registry_probe.coverage_command
    assert "test_raw_model_spec_loads_config_payload_when_not_supplied" in registry_probe.coverage_command
    assert "test_has_mlx_signal_falls_back_to_config_text_for_empty_supplied_payload" in registry_probe.coverage_command
    assert "test_has_mlx_signal_skips_config_text_fallback_for_nonempty_payload_without_mlx_signal" in registry_probe.coverage_command
    assert "test_metadata_payload_has_mlx_signal_does_not_request_sorted_json" in registry_probe.coverage_command
    assert "test_has_mlx_signal_config_payload_fast_path_does_not_request_sorted_json" in registry_probe.coverage_command
    assert "scripts/changed_scope_coverage.py" in registry_probe.coverage_command

    assert maintenance_probe is not None
    assert "test_measure_vlm_latency_metrics_reuse_single_sorted_total_latency_vector" in maintenance_probe.test_command
    assert "test_image_latency_metrics_reuse_single_sorted_job_latency_vector" in maintenance_probe.test_command
    assert "test_measure_vlm_latency_metrics_reuse_single_sorted_total_latency_vector" in maintenance_probe.coverage_command
    assert "test_image_latency_metrics_reuse_single_sorted_job_latency_vector" in maintenance_probe.coverage_command

    assert swift_probe is not None
    assert "MelixCLIRunnerTests/(" in swift_probe.test_command
    assert "MelixCLITests/MelixCLIRunnerTests" not in swift_probe.test_command
    swift_verification_tests = (
        "jsonV1WrapsCommandResultsInAStableEnvelope",
        "jsonV1ErrorEnvelopesAreMachineReadable",
        "jsonMetricPatchingRejectsMissingPlaceholders",
        "jsonMetricPatchingPreservesUserArtifactStringsThatLookLikeTheOldSentinel",
    )
    swift_probe_tests = (
        "jsonV1WrapsCommandResultsInAStableEnvelope",
        "jsonV1ErrorEnvelopesAreMachineReadable",
        "jsonMetricPatchingPreservesUserArtifactStringsThatLookLikeTheOldSentinel",
    )
    for test_name in swift_verification_tests:
        assert test_name in swift_probe.test_command
        assert test_name in swift_probe.coverage_command
    for test_name in swift_probe_tests:
        assert test_name in swift_probe.probe_command
    assert "jsonMetricPatchingRejectsMissingPlaceholders" not in swift_probe.probe_command
    assert swift_probe.probe_command.startswith("python3 - <<'PY'")
    assert "stdout=sys.stderr" in swift_probe.probe_command
    assert "stderr=sys.stderr" in swift_probe.probe_command


def test_load_probe_registry_uses_absolute_cache_key_without_resolving(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "probe-registry.json"
    registry_path.write_text(
        json.dumps(
            [
                {
                    "id": "demo",
                    "name": "Demo",
                    "probe_impl": "command_json",
                    "probe_command": "python3 -c \"import json; print(json.dumps({'elapsed_ms_mean': 1.0}))\"",
                    "metrics": [{"key": "elapsed_ms_mean", "unit": "ms", "direction": "lower_is_better"}],
                }
            ]
        ),
        encoding="utf-8",
    )

    def fail_resolve(self: Path, *args: object, **kwargs: object) -> Path:  # pragma: no cover
        raise AssertionError("load_probe_registry should avoid Path.resolve on the cache hot path")

    monkeypatch.setattr(Path, "resolve", fail_resolve)

    first = load_probe_registry(registry_path)
    second = load_probe_registry(registry_path)
    scope = build_scope_report(registry_path=registry_path, changed_files=["worker.py"])

    assert second is first
    assert scope["selected_count"] == 0


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


def test_load_probe_registry_reuses_cached_payload_when_file_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "probe-registry.json"
    registry_path.write_text(
        json.dumps(
            [
                {
                    "id": "demo",
                    "name": "Demo",
                    "probe_impl": "command_json",
                    "probe_command": "python3 -c \"import json; print(json.dumps({'elapsed_ms_mean': 1.0}))\"",
                    "metrics": [{"key": "elapsed_ms_mean", "unit": "ms", "direction": "lower_is_better"}],
                }
            ]
        ),
        encoding="utf-8",
    )
    read_calls = 0
    original_read_bytes = Path.read_bytes

    def fail_read_text(self: Path, *args: object, **kwargs: object) -> str:  # pragma: no cover
        raise AssertionError("load_probe_registry should read JSON bytes without text decoding")

    def tracked_read_bytes(self: Path, *args: object, **kwargs: object) -> bytes:
        nonlocal read_calls
        if self == registry_path:
            read_calls += 1
        return original_read_bytes(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_read_text)
    monkeypatch.setattr(Path, "read_bytes", tracked_read_bytes)

    first = load_probe_registry(registry_path)
    second = load_probe_registry(registry_path)

    assert read_calls == 1
    assert second is first


def test_build_scope_report_reuses_scope_cached_registry_without_double_stat(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "probe-registry.json"
    registry_path.write_text(
        json.dumps(
            [
                {
                    "id": "demo",
                    "name": "Demo",
                    "watch_globs": [
                        "services/mlx-worker-python/worker/productization/pr_scoped_performance.py"
                    ],
                    "probe_impl": "command_json",
                    "probe_command": "python3 -c \"import json; print(json.dumps({'elapsed_ms_mean': 1.0}))\"",
                    "metrics": [{"key": "elapsed_ms_mean", "unit": "ms", "direction": "lower_is_better"}],
                }
            ]
        ),
        encoding="utf-8",
    )
    stat_calls = 0
    original_stat = Path.stat
    cache = pr_scoped_performance_module._PROBE_REGISTRY_CACHE
    pr_scoped_performance_module._load_probe_registry_for_scope_cached.cache_clear()
    cache.clear()

    def tracked_stat(self: Path, *args: object, **kwargs: object) -> os.stat_result:
        nonlocal stat_calls
        if self == registry_path:
            stat_calls += 1
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", tracked_stat)

    try:
        first = build_scope_report(
            registry_path=registry_path,
            changed_files=["services/mlx-worker-python/worker/productization/pr_scoped_performance.py"],
        )
        second = build_scope_report(
            registry_path=registry_path,
            changed_files=["services/mlx-worker-python/worker/productization/pr_scoped_performance.py"],
        )
    finally:
        pr_scoped_performance_module._load_probe_registry_for_scope_cached.cache_clear()
        cache.clear()

    assert stat_calls == 2
    assert first["selected_count"] == 1
    assert second["selected_probes"] == first["selected_probes"]


def test_load_probe_registry_refreshes_cache_when_file_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "probe-registry.json"
    registry_path.write_text(
        json.dumps(
            [
                {
                    "id": "demo-a",
                    "name": "Demo A",
                    "probe_impl": "command_json",
                    "probe_command": "python3 -c \"import json; print(json.dumps({'elapsed_ms_mean': 1.0}))\"",
                    "metrics": [{"key": "elapsed_ms_mean", "unit": "ms", "direction": "lower_is_better"}],
                }
            ]
        ),
        encoding="utf-8",
    )
    read_calls = 0
    original_read_bytes = Path.read_bytes

    def tracked_read_bytes(self: Path, *args: object, **kwargs: object) -> bytes:
        nonlocal read_calls
        if self == registry_path:
            read_calls += 1
        return original_read_bytes(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", tracked_read_bytes)

    first = load_probe_registry(registry_path)
    time.sleep(0.001)
    registry_path.write_text(
        json.dumps(
            [
                {
                    "id": "demo-b",
                    "name": "Demo B",
                    "probe_impl": "command_json",
                    "probe_command": "python3 -c \"import json; print(json.dumps({'elapsed_ms_mean': 2.0, 'build_scope_report_ms_mean': 3.0}))\"",
                    "metrics": [
                        {"key": "elapsed_ms_mean", "unit": "ms", "direction": "lower_is_better"},
                        {"key": "build_scope_report_ms_mean", "unit": "ms", "direction": "lower_is_better"},
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    second = load_probe_registry(registry_path)

    assert read_calls == 2
    assert first[0].probe_id == "demo-a"
    assert second[0].probe_id == "demo-b"


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


def test_code_eval_stdio_probe_script_emits_metrics(capsys: pytest.CaptureFixture[str]) -> None:
    probe_script = runpy.run_path(str(REPO_ROOT / "scripts/code_eval_stdio_probe.py"))

    probe_script["main"]()
    metrics = json.loads(capsys.readouterr().out)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["stdio_stat_calls_mean"] == 6000.0
    assert metrics["output_limit_exceeded_mean"] == 1.0
    assert metrics["tail_chars_mean"] > 0


def test_code_eval_code_block_extract_probe_script_emits_metrics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe_script = runpy.run_path(str(REPO_ROOT / "scripts/code_eval_code_block_extract_probe.py"))

    probe_script["main"]()
    metrics = json.loads(capsys.readouterr().out)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["block_count"] == 2500.0
    assert metrics["sample_count"] == 7.0
    assert metrics["extracted_chars_mean"] > 0


def test_probe_smokes_return_metrics_against_current_repo() -> None:
    benchmark_metrics = _probe_benchmark_evaluation_report(REPO_ROOT)
    benchmark_export_metrics = _probe_benchmark_export_run_scan(REPO_ROOT)
    benchmark_queue_metrics = _probe_benchmark_queue_cache(REPO_ROOT)
    closure_metrics = _probe_closure_audit(REPO_ROOT)
    rerank_metrics = _probe_deterministic_rerank_query_context_reuse(REPO_ROOT)
    evaluation_job_id_metrics = _probe_evaluation_job_id(REPO_ROOT)
    evaluation_sample_probe_metrics = _probe_evaluation_sample_probe_aggregation(REPO_ROOT)
    evaluation_store_compare_summary_metrics = _probe_evaluation_store_compare_summary_csv_streaming(REPO_ROOT)
    evaluation_store_metrics = _probe_evaluation_store_samples_csv_streaming(REPO_ROOT)
    scope_matcher_metrics = _probe_pr_scoped_scope_matcher(REPO_ROOT)
    training_dataset_metrics = _probe_training_dataset_token_percentiles(REPO_ROOT)
    model_ops_bundle_metrics = _probe_model_ops_bundle_artifact_bytes(REPO_ROOT)

    assert benchmark_metrics["elapsed_ms_mean"] > 0
    assert benchmark_metrics["peak_bytes_mean"] > 0
    assert benchmark_metrics["row_count"] > 0
    assert benchmark_export_metrics["elapsed_ms_mean"] > 0
    assert benchmark_export_metrics["per_run_ms_mean"] > 0
    assert benchmark_export_metrics["benchmark_job_count"] == 241.0
    assert benchmark_export_metrics["evaluation_job_count"] == 241.0
    assert benchmark_export_metrics["evaluation_result_count"] == 241.0
    assert benchmark_export_metrics["evaluation_sample_count"] == 241.0
    assert benchmark_export_metrics["run_directory_count"] == 240.0
    assert benchmark_export_metrics["result_file_count"] == 723.0
    assert benchmark_queue_metrics["cold_json_loads"] == 128.0
    assert benchmark_queue_metrics["record_count"] == 128.0
    assert benchmark_queue_metrics["warm_json_loads_mean"] == 0.0
    assert benchmark_queue_metrics["warm_elapsed_ms_mean"] >= 0
    assert closure_metrics["elapsed_ms_mean"] > 0
    assert closure_metrics["peak_bytes_mean"] > 0
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
    assert scope_matcher_metrics["selected_probe_count_mean"] == 5.0
    assert scope_matcher_metrics["force_all_selected_mean"] == 0.0
    assert training_dataset_metrics["elapsed_ms_mean"] > 0
    assert training_dataset_metrics["peak_bytes_mean"] > 0
    assert training_dataset_metrics["sample_count"] == 20000.0
    assert training_dataset_metrics["duplicate_count"] > 0
    assert training_dataset_metrics["dirty_count"] > 0
    assert model_ops_bundle_metrics["elapsed_ms_mean"] > 0
    assert model_ops_bundle_metrics["bundle_scandir_calls_mean"] == 0.0
    assert model_ops_bundle_metrics["sample_count"] > 0


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
    assert metrics["benchmark_job_count"] == 241.0
    assert metrics["evaluation_job_count"] == 241.0
    assert metrics["evaluation_result_count"] == 241.0
    assert metrics["evaluation_sample_count"] == 241.0
    assert metrics["run_directory_count"] == 240.0
    assert metrics["result_file_count"] == 723.0


def _fake_benchmark_export_module(
    *,
    benchmark_job_count: int = 241,
    evaluation_job_count: int = 241,
    benchmark_result_count: int = 723,
    evaluation_result_count: int = 241,
    evaluation_sample_count: int = 241,
    summary_csv_job_count: int = 241,
) -> type[object]:
    class FakeBenchmarkExportModule:
        @staticmethod
        def build_export_bundle(path: Path) -> dict[str, object]:
            del path
            return {
                "benchmark_jobs": [object()] * benchmark_job_count,
                "evaluation_jobs": [object()] * evaluation_job_count,
                "benchmark_results": [object()] * benchmark_result_count,
                "evaluation_results": [object()] * evaluation_result_count,
                "evaluation_samples": [object()] * evaluation_sample_count,
            }

        @staticmethod
        def build_benchmark_summary_csv(artifacts: dict[str, object]) -> str:
            del artifacts
            return "job_id\n" + "\n".join(f"bench-{index}" for index in range(summary_csv_job_count)) + (
                "\n" if summary_csv_job_count else ""
            )

    return FakeBenchmarkExportModule


def _patch_benchmark_export_probe_module(
    monkeypatch: pytest.MonkeyPatch,
    fake_module: type[object],
) -> None:
    monkeypatch.setattr(
        pr_scoped_performance_module,
        "_load_repo_module",
        lambda path, unique_name: fake_module,
    )


def test_probe_benchmark_export_run_scan_rejects_unexpected_job_count(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_module = _fake_benchmark_export_module(benchmark_job_count=0)
    _patch_benchmark_export_probe_module(monkeypatch, fake_module)

    with pytest.raises(ValueError, match="unexpected benchmark job count"):
        _probe_benchmark_export_run_scan(REPO_ROOT)


def test_probe_benchmark_export_run_scan_rejects_unexpected_evaluation_job_count(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_module = _fake_benchmark_export_module(evaluation_job_count=0)
    _patch_benchmark_export_probe_module(monkeypatch, fake_module)

    with pytest.raises(ValueError, match="unexpected evaluation job count"):
        _probe_benchmark_export_run_scan(REPO_ROOT)


def test_probe_benchmark_export_run_scan_rejects_unexpected_result_count(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_module = _fake_benchmark_export_module(benchmark_result_count=0)
    _patch_benchmark_export_probe_module(monkeypatch, fake_module)

    with pytest.raises(ValueError, match="unexpected benchmark result count"):
        _probe_benchmark_export_run_scan(REPO_ROOT)


def test_probe_benchmark_export_run_scan_rejects_unexpected_summary_csv_count(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_module = _fake_benchmark_export_module(summary_csv_job_count=0)
    _patch_benchmark_export_probe_module(monkeypatch, fake_module)

    with pytest.raises(ValueError, match="unexpected summary CSV line count"):
        _probe_benchmark_export_run_scan(REPO_ROOT)


def test_dispatch_probe_impl_supports_benchmark_queue_probe() -> None:
    probe = ProbeDefinition(
        probe_id="benchmark-queue-decoded-record-cache",
        name="Benchmark queue decoded-record cache",
        runner="ubuntu-latest",
        watch_globs=("services/mlx-worker-python/worker/productization/benchmark_queue.py",),
        test_command="true",
        coverage_command="true",
        probe_impl="benchmark_queue_cache",
        probe_command='python3 -c "{}"',
        metrics=(MetricDefinition(key="warm_elapsed_ms_mean", unit="ms", direction="lower_is_better"),),
    )

    metrics = _dispatch_probe_impl(probe=probe, repo_root=REPO_ROOT)

    assert metrics["cold_elapsed_ms"] >= 0
    assert metrics["cold_json_loads"] == 128.0
    assert metrics["record_count"] == 128.0
    assert metrics["warm_json_loads_mean"] == 0.0
    assert metrics["warm_elapsed_ms_mean"] >= 0


def test_probe_benchmark_queue_cache_rejects_unexpected_record_count(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeBenchmarkQueueModule:
        json = json

        class BenchmarkQueueStore:
            def list_records(self, *, queue_root: Path) -> list[object]:
                del queue_root
                return []

        class BenchmarkQueueRecord:
            def __init__(self, **kwargs: object) -> None:
                self._payload = kwargs

            def to_dict(self) -> dict[str, object]:
                return dict(self._payload)

    monkeypatch.setattr(pr_scoped_performance_module, "_load_repo_module", lambda path, unique_name: FakeBenchmarkQueueModule)

    with pytest.raises(ValueError, match="unexpected benchmark queue record count"):
        _probe_benchmark_queue_cache(REPO_ROOT)


def test_worker_registry_probe_script_emits_metrics(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(REPO_ROOT / "scripts/worker_registry_resident_probe.py"), run_name="__main__")

    assert excinfo.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["elapsed_ms_mean"] > 0
    assert payload["loaded_model_listing_elapsed_ms_mean"] > 0
    assert payload["loaded_model_listing_sort_calls_mean"] > 0
    assert payload["preloaded_model_count"] == 2000.0
    assert payload["loop_count"] == 250.0
    assert payload["request_count"] == 3000.0
    assert payload["request_stats_elapsed_ms_mean"] > 0
    assert payload["resident_bytes_mean"] > 0
    assert payload["sample_count"] == 3.0


def test_startup_signals_probe_script_emits_metrics(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(REPO_ROOT / "scripts/startup_signals_log_probe.py"), run_name="__main__")

    assert excinfo.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["conflict_elapsed_ms_mean"] > 0
    assert payload["conflict_log_reads_mean"] == 1.0
    assert payload["control_crash_elapsed_ms_mean"] > 0
    assert payload["control_crash_log_reads_mean"] == 1.0
    assert payload["worker_crash_elapsed_ms_mean"] > 0
    assert payload["worker_crash_log_reads_mean"] == 1.0
    assert payload["sample_count"] == 5.0


def test_job_registry_probe_script_emits_metrics(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(REPO_ROOT / "scripts/job_registry_derived_model_probe.py"), run_name="__main__")

    assert excinfo.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["active_manifest_elapsed_ms_mean"] > 0
    assert payload["resolve_target_elapsed_ms_mean"] > 0
    assert payload["restore_elapsed_ms_mean"] > 0
    assert payload["restore_elapsed_ms_min"] > 0
    assert payload["active_manifest_count"] == 960.0
    assert payload["removed_count"] == 240.0
    assert payload["restored_job_count"] == 880.0
    assert payload["sample_count"] == 6.0


def test_job_registry_restore_probe_script_emits_metrics(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(REPO_ROOT / "scripts/job_registry_restore_probe.py"), run_name="__main__")

    from worker.model_ops.job_registry import ModelOpsJobRegistry

    assert excinfo.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["restore_elapsed_ms_mean"] > 0
    assert payload["per_manifest_ms_mean"] > 0
    assert payload["job_count"] == 15000.0
    assert payload["train_manifest_count"] == 5000.0
    assert payload["activate_manifest_count"] == 5000.0
    assert payload["remove_manifest_count"] == 5000.0
    assert payload["sample_count"] == 8.0
    assert ModelOpsJobRegistry()._read_manifest_dict(tmp_path / "missing.json") == {}


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


def test_real_model_support_hf_cache_probe_script_emits_metrics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(REPO_ROOT / "scripts/real_model_support_hf_cache_probe.py"), run_name="__main__")

    assert excinfo.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["elapsed_ms_mean"] > 0
    assert payload["peak_bytes_mean"] > 0
    assert payload["sample_count"] == 7.0
    assert payload["snapshot_count"] == 6000.0
    assert payload["selected_latest_snapshot"] == 5999.0


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
    assert metrics["selected_probe_count_mean"] == 5.0
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


def test_dispatch_probe_impl_supports_model_ops_bundle_probe() -> None:
    probe = ProbeDefinition(
        probe_id="model-ops-bundle-artifact-byte-accounting",
        name="Model ops bundle artifact byte accounting",
        runner="ubuntu-latest",
        watch_globs=("services/mlx-worker-python/worker/model_ops/conversion_pipeline.py",),
        test_command="true",
        coverage_command="true",
        probe_impl="model_ops_bundle_artifact_bytes",
        probe_command='python3 -c "{}"',
        metrics=(MetricDefinition(key="elapsed_ms_mean", unit="ms", direction="lower_is_better"),),
    )

    metrics = _dispatch_probe_impl(probe=probe, repo_root=REPO_ROOT)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["bundle_scandir_calls_mean"] == 0.0
    assert metrics["sample_count"] > 0


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


def test_dispatch_probe_impl_supports_registry_cache_probe() -> None:
    probe = next(
        probe
        for probe in load_probe_registry(REGISTRY_PATH)
        if probe.probe_id == "pr-scoped-performance-registry-cache"
    )

    metrics = _dispatch_probe_impl(probe=probe, repo_root=REPO_ROOT)

    assert metrics["load_probe_registry_ms_mean"] > 0
    assert metrics["cold_load_probe_registry_ms_mean"] > 0
    assert metrics["build_scope_report_ms_mean"] > 0
    assert metrics["sample_count"] == 6.0


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


def test_command_and_verification_helpers_cover_skip_and_failure_paths(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    coverage_stdout = "TOTAL  10  0  100%\n"
    command_result = _run_command(
        "python3 -c \"import sys; print('TOTAL  10  0  100%'); print('progress line', file=sys.stderr)\"",
        cwd=tmp_path,
    )
    assert command_result["coverage_pct"] == 100.0
    command_stderr = capsys.readouterr().err
    assert "[pr-scoped-performance] starting command" in command_stderr
    assert "TOTAL  10  0  100%" in command_stderr
    assert "progress line" in command_stderr
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


def test_command_summary_keeps_ci_heartbeats_compact() -> None:
    assert _summarize_command("python3 - <<'PY'\nprint('x')\nPY") == "python3 - <<'PY' ..."
    assert _summarize_command(" \n ") == "<empty command>"

    long_summary = _summarize_command("python3 -c " + "x" * 300, max_length=80)
    assert len(long_summary) <= 80
    assert long_summary.endswith(" ...")


def test_run_command_emits_heartbeat_for_silent_command(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(pr_scoped_performance_module, "_COMMAND_HEARTBEAT_SECONDS", 0.01)

    result = _run_command("python -c \"import time; time.sleep(0.05); print('done')\"", cwd=tmp_path)

    assert result["ok"] is True
    stderr = capsys.readouterr().err
    assert "still running after" in stderr
    assert "python -c" in stderr


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
            "python -c \"import json; "
            "print(json.dumps({'elapsed_ms_mean': 12.5, 'iteration_count': 3}))\""
        ),
        metrics=(MetricDefinition(key="elapsed_ms_mean", unit="ms", direction="lower_is_better"),),
    )

    metrics = _probe_command_json(probe=probe, repo_root=tmp_path)

    assert metrics == {"elapsed_ms_mean": 12.5, "iteration_count": 3.0}


def test_evaluation_latency_percentile_probe_command_emits_metrics() -> None:
    probe = next(
        probe
        for probe in load_probe_registry(REGISTRY_PATH)
        if probe.probe_id == "evaluation-latency-percentile-vector-reuse"
    )

    metrics = _probe_command_json(probe=probe, repo_root=REPO_ROOT)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["sorted_calls_mean"] == 1.0
    assert metrics["sample_count"] == 12000.0
    assert metrics["iteration_count"] == 160.0
    assert metrics["p95"] >= metrics["p50"]


def test_model_registry_catalog_probe_command_emits_metrics() -> None:
    probe = next(
        probe
        for probe in load_probe_registry(REGISTRY_PATH)
        if probe.probe_id == "model-registry-plain-local-manifest-stat-elision"
    )

    metrics = _probe_command_json(probe=probe, repo_root=REPO_ROOT)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["manifest_is_file_calls_mean"] == 0.0
    assert metrics["config_load_calls_mean"] == 400.0
    assert metrics["manifest_parse_calls_mean"] == 0.0
    assert metrics["discovered_model_count_mean"] == metrics["model_count"] == 400.0
    assert metrics["sample_count"] == 2.0


def test_mlx_lm_result_tail_probe_script_emits_metrics() -> None:
    probe = next(
        probe
        for probe in load_probe_registry(REGISTRY_PATH)
        if probe.probe_id == "mlx-lm-structured-result-tail-parse"
    )

    metrics = _probe_command_json(probe=probe, repo_root=REPO_ROOT)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["payload_value"] == 42.0
    assert metrics["line_count"] == 50002.0
    assert metrics["sample_count"] == 5.0


def test_lora_reward_summary_probe_script_emits_metrics() -> None:
    probe = next(
        probe
        for probe in load_probe_registry(REGISTRY_PATH)
        if probe.probe_id == "lora-reward-summary-candidate-minmax"
    )

    metrics = _probe_command_json(probe=probe, repo_root=REPO_ROOT)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["sorted_calls_mean"] == 2.0
    assert metrics["sample_count"] == 5000.0
    assert metrics["candidate_count"] == 32.0
    assert metrics["checksum"] > 0


def test_lora_reward_summary_probe_script_main_covers_checked_in_file(
    capsys: pytest.CaptureFixture[str],
) -> None:
    script_path = REPO_ROOT / "scripts" / "lora_reward_summary_probe.py"
    spec = importlib.util.spec_from_file_location("lora_reward_summary_probe_test", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.main() == 0
    payload = json.loads(capsys.readouterr().out.strip())

    assert payload["sorted_calls_mean"] == 2.0
    assert payload["sample_count"] == 5000.0
    assert payload["candidate_count"] == 32.0


def test_mlx_vlm_family_config_probe_script_emits_metrics() -> None:
    probe = next(
        probe
        for probe in load_probe_registry(REGISTRY_PATH)
        if probe.probe_id == "mlx-vlm-family-config-cache"
    )

    metrics = _probe_command_json(probe=probe, repo_root=REPO_ROOT)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["resolve_calls_mean"] >= 1.0
    assert metrics["prompt_token_count"] == 3.0
    assert metrics["iteration_count"] == 200.0
    assert metrics["sample_count"] == 5.0


def test_mlx_lm_result_tail_probe_script_main_covers_checked_in_file(capsys: pytest.CaptureFixture[str]) -> None:
    script_path = REPO_ROOT / "scripts" / "mlx_lm_result_tail_probe.py"
    spec = importlib.util.spec_from_file_location("mlx_lm_result_tail_probe_test", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.NOISE_LINE_COUNT = 32
    module.ITERATION_COUNT = 2
    module.SAMPLE_COUNT = 2

    assert module.main() == 0
    payload = json.loads(capsys.readouterr().out.strip())

    assert payload["payload_value"] == 42.0
    assert payload["sample_count"] == 2.0
    assert payload["line_count"] == 34.0


def test_mlx_vlm_family_config_probe_script_main_covers_checked_in_file(
    capsys: pytest.CaptureFixture[str],
) -> None:
    script_path = REPO_ROOT / "scripts" / "mlx_vlm_family_config_probe.py"
    spec = importlib.util.spec_from_file_location("mlx_vlm_family_config_probe_test", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ITERATION_COUNT = 8
    module.SAMPLE_COUNT = 2

    assert module.main() == 0
    payload = json.loads(capsys.readouterr().out.strip())

    assert payload["prompt_token_count"] == 3.0
    assert payload["iteration_count"] == 8.0
    assert payload["sample_count"] == 2.0
    assert payload["resolve_calls_mean"] >= 1.0


def test_mlx_vlm_gemma4_weight_presence_probe_script_emits_metrics() -> None:
    probe = next(
        probe
        for probe in load_probe_registry(REGISTRY_PATH)
        if probe.probe_id == "mlx-vlm-gemma4-weight-presence-single-pass"
    )

    metrics = _probe_command_json(probe=probe, repo_root=REPO_ROOT)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["visited_names_mean"] > 0
    assert metrics["has_vision"] == 1.0
    assert metrics["has_audio"] == 1.0


def test_mlx_vlm_gemma4_weight_presence_probe_script_main_covers_checked_in_file(
    capsys: pytest.CaptureFixture[str],
) -> None:
    script_path = REPO_ROOT / "scripts" / "mlx_vlm_gemma4_weight_presence_probe.py"
    spec = importlib.util.spec_from_file_location("mlx_vlm_gemma4_weight_presence_probe_test", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.WEIGHT_NAME_COUNT = 32
    module.ITERATION_COUNT = 2
    module.SAMPLE_COUNT = 2

    assert module.main() == 0
    payload = json.loads(capsys.readouterr().out.strip())

    assert payload["weight_name_count"] == 32.0
    assert payload["iteration_count"] == 2.0
    assert payload["sample_count"] == 2.0
    assert payload["has_vision"] == 1.0
    assert payload["has_audio"] == 1.0


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
    assert _glob_literal_prefix("services/*.py") == "services/"
    assert _glob_literal_prefix("docs/plans/file.md") == "docs/plans/file.md"
    assert _glob_literal_prefix("tests/test_[ab].py") == "tests/test_"
    assert _matches_any_glob("services/a.py", ("services/*.py",)) is True
    assert _matches_any_glob("docs/a.md", ("services/*.py",)) is False
    assert _is_relative_to(nested_path, tmp_path) is True
    assert _is_relative_to(Path("/tmp/not-child"), tmp_path) is False


def test_glob_matching_skips_regex_when_literal_prefix_misses(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_compile(glob: str):  # pragma: no cover - sentinel
        raise AssertionError(f"regex should not be compiled for prefix miss: {glob}")

    monkeypatch.setattr(pr_scoped_performance_module, "_compiled_glob_pattern", fail_compile)

    assert pr_scoped_performance_module._glob_matches_path(
        "docs/plans/scope.md",
        "services/mlx-worker-python/*.py",
    ) is False


def test_glob_matching_preserves_wildcard_semantics() -> None:
    assert pr_scoped_performance_module._glob_matches_path(
        "services/mlx-worker-python/worker/productization/pr_scoped_performance.py",
        "services/mlx-worker-python/worker/productization/*.py",
    ) is True
    assert pr_scoped_performance_module._glob_matches_path(
        "services/mlx-worker-python/tests/test_pr_scoped_performance.py",
        "services/mlx-worker-python/tests/test_pr_scoped_performance.py",
    ) is True


def test_compiled_glob_matching_preserves_prefix_short_circuit() -> None:
    matchers = (
        (
            "services/mlx-worker-python/",
            pr_scoped_performance_module._compiled_glob_pattern("services/mlx-worker-python/*.py"),
        ),
        ("docs/", pr_scoped_performance_module._compiled_glob_pattern("docs/**/*.md")),
    )

    assert pr_scoped_performance_module._matches_any_compiled_glob(
        "services/mlx-worker-python/pr_scoped_performance.py",
        matchers,
    ) is True
    assert pr_scoped_performance_module._matches_any_compiled_glob(
        "infra/perf/pr_scoped_probes.json",
        matchers,
    ) is False


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


def test_performance_report_script_load_results_avoids_exists_stat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "result.json").write_text(json.dumps({"probe": {"id": "result"}}), encoding="utf-8")

    def fail_exists(self: Path):  # pragma: no cover - sentinel
        raise AssertionError("_load_results should let os.scandir perform the existence check")

    monkeypatch.setattr(Path, "exists", fail_exists)
    report_script = runpy.run_path(str(REPO_ROOT / "scripts/pr_scoped_performance_report.py"))

    loaded = report_script["_load_results"](results_dir)

    assert loaded == [{"probe": {"id": "result"}}]



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



def test_scope_cli_loads_changed_files_with_binary_json_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    changed_files_path = tmp_path / "changed-files.json"
    changed_files_path.write_text(json.dumps(["scripts/pr_scoped_performance_scope.py"]), encoding="utf-8")
    scope_script = runpy.run_path(str(REPO_ROOT / "scripts/pr_scoped_performance_scope.py"))
    load_changed_files = scope_script["load_changed_files"]

    def fail_read_text(self: Path, *args: object, **kwargs: object) -> str:
        raise AssertionError("scope changed-files loader should use read_bytes()")  # pragma: no cover

    monkeypatch.setattr(scope_script["Path"], "read_text", fail_read_text)

    assert load_changed_files(changed_files_path) == ["scripts/pr_scoped_performance_scope.py"]

    changed_files_path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
    with pytest.raises(ValueError, match="changed files payload must be a JSON list"):
        load_changed_files(changed_files_path)


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
