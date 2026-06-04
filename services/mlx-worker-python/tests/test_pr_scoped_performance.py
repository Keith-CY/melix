from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import re
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
    _coverage_paths_by_probe_id,
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
    _probe_id_to_index,
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
    coverage_paths_for_probe,
    load_probe_registry,
    render_markdown_report,
    render_terminal_report,
    run_probe_job,
    write_report_outputs,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = REPO_ROOT / "infra/perf/pr_scoped_probes.json"
DATASET_REGISTRY_SELECTED_PROBE_IDS = [
    "dataset-registry-limited-read-streaming",
    "dataset-registry-snapshot-inference-single-pass",
    "dataset-registry-preview-limit-short-circuit",
]
MLX_AUDIO_RUNTIME_SELECTED_PROBE_IDS = [
    "mlx-audio-speech-signature-cache",
    "mlx-audio-wav-streaming-pcm",
    "mlx-audio-local-uri-zero-copy-preprocess",
    "mlx-audio-generate-signature-cache",
]
SCOPE_MATCHER_SELECTED_PROBE_IDS = [
    "benchmark-export-run-scan-single-pass",
    "evaluation-job-id-high-water-mark",
    "evaluation-sample-probe-aggregation",
    "evaluation-answer-normalization-fast-path",
    "evaluation-latency-percentile-vector-reuse",
    "evaluation-dialogue-diagnostics-top-k",
    "download-pipeline-directory-size-single-stat",
]


def _selected_probe_ids(scope: dict[str, object]) -> list[str]:
    return [probe["id"] for probe in _dict_list(scope["selected_probes"])]


@pytest.fixture()
def benchmark_scope() -> dict[str, object]:
    return build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py"],
    )


def test_scope_report_selects_event_extraction_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/productization/event_extraction.py"],
    )

    assert scope["selected_count"] == 4
    assert {probe["id"] for probe in scope["selected_probes"]} == {
        "event-extraction-alignment-accepted-edge-cache",
        "event-extraction-semantic-value-group-cache",
        "event-extraction-group-actor-alias-cache",
        "event-extraction-response-json-fence-trim",
    }


def test_scope_report_selects_hub_catalog_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/model_ops/hub_catalog.py"],
    )

    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert scope["selected_count"] == 3
    assert probe_ids == {
        "hub-catalog-tag-normalization-single-pass",
        "hub-catalog-next-cursor-fast-parse",
        "hub-catalog-size-hint-regex-precompile",
    }


def test_scope_report_selects_stream_assembler_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/runtime/stream_assembler.py"],
    )

    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert scope["selected_count"] == 3
    assert probe_ids == {
        "stream-assembler-parser-mode-cache",
        "stream-assembler-structural-prefix-cache",
        "stream-assembler-token-byte-fast-decode",
    }


def test_scope_report_selects_runtime_utils_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/runtime/runtime_utils.py"],
    )

    assert scope["selected_count"] == 3
    assert _selected_probe_ids(scope) == [
        "runtime-utils-kwarg-signature-cache",
        "runtime-utils-package-version-cache",
        "runtime-utils-top-level-weight-streaming",
    ]


def test_scope_report_selects_engine_generate_usage_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/engine/engine_core.py"],
    )

    assert scope["selected_count"] == 1
    assert _selected_probe_ids(scope) == ["engine-generate-usage-token-elision"]


def test_scope_report_selects_report_evidence_gate_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/productization/report_evidence_gate.py"],
    )

    assert scope["selected_count"] == 1
    assert _selected_probe_ids(scope) == ["report-evidence-gate-run-kind-set-membership"]


def test_report_evidence_gate_run_kind_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_REPORT_EVIDENCE_RUN_KIND_ITERATIONS", "20")
    monkeypatch.setenv("MELIX_REPORT_EVIDENCE_RUN_KIND_SAMPLES", "1")
    probe_script = runpy.run_path(str(REPO_ROOT / "scripts/report_evidence_gate_run_kind_probe.py"))

    assert probe_script["main"]() == 0

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["elapsed_ms_mean"] >= 0.0
    assert metrics["match_count"] == metrics["iterations"] * metrics["sample_count"]
    assert metrics["metric_prefix_match_count"] == metrics["iterations"] * metrics["sample_count"]
    assert metrics["target_field_match_count"] == metrics["iterations"] * metrics["sample_count"]
    assert metrics["run_kind_elapsed_ms_mean"] >= 0.0
    assert metrics["metric_prefix_elapsed_ms_mean"] >= 0.0
    assert metrics["target_field_elapsed_ms_mean"] >= 0.0
    assert metrics["run_kind_count"] == 65.0
    assert metrics["metric_prefix_count"] == 65.0
    assert metrics["target_field_count"] == 65.0
    assert metrics["metrics_per_call"] == 80.0
    assert metrics["targets_per_call"] == 80.0


def test_scope_report_selects_dataset_version_listing_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/productization/dataset_preparation.py"],
    )

    selected_ids = _selected_probe_ids(scope)
    assert "dataset-version-listing-scandir" in selected_ids
    assert "dataset-quality-lengths-chain" in selected_ids
    assert "dataset-source-records-scandir" in selected_ids


def test_scope_report_selects_lora_aux_modules_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/model_ops/lora_runtime_metadata.py"],
    )

    assert _selected_probe_ids(scope) == ["lora-aux-modules-scandir"]


def test_scope_report_selects_trajectory_provenance_copy_elision_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/trajectory_provenance.py"],
    )

    assert _selected_probe_ids(scope) == [
        "trajectory-provenance-copy-elision",
        "trajectory-manifest-json-load",
    ]


def test_scope_report_selects_native_mtp_loader_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/runtime/native_mtp/mlx_lm_loader.py"],
    )

    assert _selected_probe_ids(scope) == ["native-mtp-loader-safetensor-scandir"]


def test_lora_aux_modules_scandir_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_LORA_AUX_MODULES_PROBE_NOISE_FILES", "5")
    monkeypatch.setenv("MELIX_LORA_AUX_MODULES_PROBE_SAMPLES", "1")
    monkeypatch.setenv("MELIX_LORA_QUANTIZED_KIND_PROBE_ITERATIONS", "6")
    probe_script = runpy.run_path(str(REPO_ROOT / "scripts/lora_aux_modules_scandir_probe.py"))

    assert probe_script["main"]() == 0

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["elapsed_ms_mean"] >= 0.0
    assert metrics["noise_file_count"] == 5.0
    assert metrics["scandir_calls_mean"] == 1.0
    assert metrics["processor_resume_baseline_elapsed_ms_mean"] >= 0.0
    assert metrics["processor_resume_optimized_elapsed_ms_mean"] >= 0.0
    assert metrics["processor_resume_isfile_calls_mean"] == 2.0
    assert metrics["quantized_kind_baseline_elapsed_ms_mean"] >= 0.0
    assert metrics["quantized_kind_optimized_elapsed_ms_mean"] >= 0.0
    assert metrics["quantized_kind_iteration_count"] == 6.0


def test_lora_processor_resume_probe_baseline_modes(tmp_path: Path) -> None:
    probe_script = runpy.run_path(str(REPO_ROOT / "scripts/lora_aux_modules_scandir_probe.py"))
    baseline_processor_resume_mode = probe_script["_baseline_processor_resume_mode"]
    base_model_dir = tmp_path / "base-model"
    base_model_dir.mkdir()

    assert baseline_processor_resume_mode(base_model_dir) == "missing"
    (base_model_dir / "tokenizer_config.json").write_text("{}\n", encoding="utf-8")
    assert baseline_processor_resume_mode(base_model_dir) == "tokenizer_only"
    (base_model_dir / "preprocessor_config.json").write_text("{}\n", encoding="utf-8")
    assert baseline_processor_resume_mode(base_model_dir) == "preprocessor_config"
    (base_model_dir / "processor_config.json").write_text("{}\n", encoding="utf-8")
    assert baseline_processor_resume_mode(base_model_dir) == "processor_config"


def test_trajectory_provenance_copy_elision_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_TRAJECTORY_PROVENANCE_PROBE_ITERATIONS", "10")
    monkeypatch.setenv("MELIX_TRAJECTORY_PROVENANCE_PROBE_SAMPLES", "1")
    monkeypatch.setenv("MELIX_TRAJECTORY_PROVENANCE_PROBE_COMPONENTS", "4")
    probe_script = runpy.run_path(str(REPO_ROOT / "scripts/trajectory_provenance_copy_elision_probe.py"))

    assert probe_script["main"]() == 0

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["baseline_elapsed_ms_mean"] >= 0.0
    assert metrics["optimized_elapsed_ms_mean"] >= 0.0
    assert metrics["elapsed_ms_mean"] == metrics["optimized_elapsed_ms_mean"]
    assert metrics["sample_count"] == 1.0
    assert metrics["iteration_count"] == 10.0
    assert metrics["component_count"] == 4.0


def test_trajectory_manifest_json_load_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MELIX_TRAJECTORY_MANIFEST_JSON_PROBE_ITERATIONS", "10")
    monkeypatch.setenv("MELIX_TRAJECTORY_MANIFEST_JSON_PROBE_SAMPLES", "1")
    monkeypatch.setenv("MELIX_TRAJECTORY_MANIFEST_JSON_PROBE_COMPONENTS", "4")
    probe_script = runpy.run_path(str(REPO_ROOT / "scripts/trajectory_manifest_json_load_probe.py"))

    metrics = probe_script["run_probe"]()

    assert metrics["old_mean_ms"] >= 0.0
    assert metrics["new_mean_ms"] >= 0.0
    assert metrics["elapsed_ms_mean"] == metrics["new_mean_ms"]
    assert metrics["sample_count"] == 1.0
    assert metrics["iteration_count"] == 10.0
    assert metrics["component_count"] == 4.0


def test_native_mtp_loader_safetensor_scandir_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MELIX_NATIVE_MTP_LOADER_MODEL_FILES", "8")
    monkeypatch.setenv("MELIX_NATIVE_MTP_LOADER_DISTRACTOR_FILES", "8")
    monkeypatch.setenv("MELIX_NATIVE_MTP_LOADER_SAMPLES", "1")
    monkeypatch.setenv("MELIX_NATIVE_MTP_LOADER_KEY_ITERATIONS", "2")
    probe_script = runpy.run_path(
        str(REPO_ROOT / "scripts/native_mtp_loader_safetensor_scandir_probe.py")
    )

    metrics = probe_script["run_probe"]()

    assert metrics["old_mean_ms"] >= 0.0
    assert metrics["new_mean_ms"] >= 0.0
    assert metrics["result_count"] == 24
    assert metrics["model_listing_old_mean_ms"] >= 0.0
    assert metrics["model_listing_new_mean_ms"] >= 0.0
    assert metrics["model_listing_result_count"] == 10
    assert metrics["extra_result_count"] == 8
    assert metrics["model_files"] == 8
    assert metrics["distractor_files"] == 8
    assert metrics["duplicate_mtp_entries"] == 8
    assert metrics["key_count"] == 26
    assert metrics["key_true_count"] == 17
    assert metrics["key_iterations"] == 2
    assert metrics["key_old_mean_ms"] >= 0.0
    assert metrics["key_new_mean_ms"] >= 0.0


def test_dataset_version_listing_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_DATASET_VERSION_LISTING_PROBE_COUNT", "5")
    monkeypatch.setenv("MELIX_DATASET_VERSION_LISTING_PROBE_SAMPLES", "1")
    probe_script = runpy.run_path(str(REPO_ROOT / "scripts/dataset_version_listing_probe.py"))

    assert probe_script["main"]() == 0

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["elapsed_ms_mean"] >= 0.0
    assert metrics["elapsed_ms_p95"] >= 0.0
    assert metrics["sample_count"] == 1.0
    assert metrics["version_count"] == 5.0


def test_dataset_quality_lengths_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_DATASET_QUALITY_LENGTHS_TRAIN_ROWS", "5")
    monkeypatch.setenv("MELIX_DATASET_QUALITY_LENGTHS_VALIDATION_ROWS", "2")
    monkeypatch.setenv("MELIX_DATASET_QUALITY_LENGTHS_SAMPLES", "1")
    probe_script = runpy.run_path(str(REPO_ROOT / "scripts/dataset_quality_lengths_probe.py"))

    assert probe_script["main"]() == 0

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["elapsed_ms_mean"] >= 0.0
    assert metrics["elapsed_ms_p95"] >= 0.0
    assert metrics["sample_count"] == 1.0
    assert metrics["train_row_count"] == 5.0
    assert metrics["validation_row_count"] == 2.0
    assert metrics["row_count"] == 7.0
    assert metrics["mean_output_length"] > 0.0
    assert metrics["p95_output_length"] > 0.0


def test_dataset_source_records_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_DATASET_SOURCE_RECORDS_PROBE_DIRS", "3")
    monkeypatch.setenv("MELIX_DATASET_SOURCE_RECORDS_PROBE_FILES_PER_DIR", "4")
    monkeypatch.setenv("MELIX_DATASET_SOURCE_RECORDS_PROBE_SAMPLES", "1")
    probe_script = runpy.run_path(str(REPO_ROOT / "scripts/dataset_source_records_probe.py"))

    assert probe_script["main"]() == 0

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["elapsed_ms_mean"] >= 0.0
    assert metrics["elapsed_ms_p95"] >= 0.0
    assert metrics["source_kind_elapsed_ms_mean"] >= 0.0
    assert metrics["source_kind_elapsed_ms_p95"] >= 0.0
    assert metrics["sample_count"] == 1.0
    assert metrics["directory_count"] == 3.0
    assert metrics["files_per_directory"] == 4.0
    assert metrics["file_count_mean"] == 12.0


def test_dataset_source_records_probe_rejects_changed_source_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe_script = runpy.run_path(str(REPO_ROOT / "scripts/dataset_source_records_probe.py"))
    monkeypatch.setattr(probe_script["dataset_preparation"], "_source_kind", lambda path: None)

    with pytest.raises(RuntimeError, match="source kind classification changed"):
        probe_script["measure"](directory_count=1, files_per_directory=1, samples=1)


def test_scope_report_selects_tool_registry_schema_bytes_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/runtime/tool_registry.py"],
    )

    assert scope["selected_count"] == 4
    assert _selected_probe_ids(scope) == [
        "tool-registry-schema-bytes-cache",
        "tool-registry-select-name-index-cache",
        "tool-registry-names-snapshot-cache",
        "tool-registry-openai-tools-template-cache",
    ]


def test_tool_registry_schema_bytes_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_TOOL_REGISTRY_METRICS_ITERATIONS", "20")
    monkeypatch.setenv("MELIX_TOOL_REGISTRY_METRICS_SAMPLES", "1")

    probe_script = runpy.run_path(str(REPO_ROOT / "scripts/tool_registry_schema_bytes_probe.py"))

    assert probe_script["main"]() == 0

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["schema_bytes"] > 0.0
    assert metrics["elapsed_ms_mean"] >= 0.0
    assert metrics["schema_payload_elapsed_ms_mean"] >= 0.0
    assert metrics["json_schema_calls_mean"] == 0.0
    assert metrics["schema_byte_count_calls_mean"] == 0.0
    assert metrics["built_in_tool_config_elapsed_ms_mean"] >= 0.0
    assert metrics["built_in_tool_config_distinct_objects_mean"] == 20.0
    assert metrics["partial_selection_tool_config_elapsed_ms_mean"] >= 0.0


def test_tool_registry_select_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_TOOL_REGISTRY_SELECT_ITERATIONS", "20")
    monkeypatch.setenv("MELIX_TOOL_REGISTRY_SELECT_SAMPLES", "1")

    probe_script = runpy.run_path(str(REPO_ROOT / "scripts/tool_registry_select_probe.py"))

    assert probe_script["main"]() == 0

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["elapsed_ms_mean"] >= 0.0
    assert metrics["select_calls_mean"] == 20.0
    assert metrics["selection_case_count"] == 5.0
    assert metrics["full_list_self_hits_mean"] == 4.0
    assert metrics["full_config_template_elapsed_ms_mean"] >= 0.0
    assert metrics["full_config_template_hits_mean"] == 4.0
    assert metrics["missing_selection_elapsed_ms_mean"] >= 0.0
    assert metrics["missing_selection_errors_mean"] == 4.0


def test_tool_registry_names_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_TOOL_REGISTRY_NAMES_ITERATIONS", "20")
    monkeypatch.setenv("MELIX_TOOL_REGISTRY_NAMES_SAMPLES", "1")

    probe_script = runpy.run_path(str(REPO_ROOT / "scripts/tool_registry_names_probe.py"))

    assert probe_script["main"]() == 0

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["elapsed_ms_mean"] >= 0.0
    assert metrics["registry_factory_elapsed_ms_mean"] >= 0.0
    assert metrics["names_calls_mean"] == 20.0
    assert metrics["same_names_object_calls_mean"] == 20.0


def test_tool_registry_openai_tools_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_TOOL_REGISTRY_OPENAI_TOOLS_ITERATIONS", "20")
    monkeypatch.setenv("MELIX_TOOL_REGISTRY_OPENAI_TOOLS_SAMPLES", "1")

    probe_script = runpy.run_path(str(REPO_ROOT / "scripts/tool_registry_openai_tools_probe.py"))

    assert probe_script["main"]() == 0

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["elapsed_ms_mean"] >= 0.0
    assert metrics["descriptor_as_openai_tool_calls_mean"] == 0.0
    assert metrics["isolated_payload_calls_mean"] == 20.0


def test_scope_report_selects_integration_swift_binary_resolution_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["tests/integration/helpers.py"],
    )

    assert scope["selected_count"] == 1
    assert _selected_probe_ids(scope) == ["integration-swift-binary-resolution-scandir"]


def test_scope_report_selects_same_cohort_batching_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["scripts/same_cohort_batching_probe.py"],
    )

    assert scope["selected_count"] == 1
    assert _selected_probe_ids(scope) == ["same-cohort-batching-probe-evidence"]


def test_same_cohort_batching_probe_metrics_are_numeric(tmp_path: Path) -> None:
    payload = {
        "admission": {
            "scheduler_admission_cohort_size": 2,
            "scheduler_admission_active_cohorts": 1,
            "scheduler_continuous_batch_size": 2,
            "scheduler_continuous_batch_active_cohorts": 1,
        },
        "worker": {
            "decode_request_ids": ["req-same-cohort-1", "req-same-cohort-2"],
            "decode_batch_size": 1,
            "model_eval_batch_size": 1,
            "max_model_step_batch_size": 1,
            "decode_loop_iterations": 2,
            "decode_batch_observation_count": 2,
            "per_batch_output_token_count": 1,
            "per_batch_output_tokens_per_second": 8,
        },
        "request_links": [
            {"worker_decode_request_id": "req-same-cohort-1"},
            {"worker_decode_request_id": "req-same-cohort-2"},
        ],
    }
    input_path = tmp_path / "same-cohort-raw.json"
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    probe = ProbeDefinition(
        probe_id="same-cohort-test",
        name="Same cohort test",
        runner="ubuntu-latest",
        watch_globs=("scripts/same_cohort_batching_probe.py",),
        test_command="true",
        coverage_command="true",
        probe_impl="command_json",
        probe_command=f"python3 scripts/same_cohort_batching_probe.py --input {input_path} --metrics",
        metrics=(
            MetricDefinition(
                key="scheduler_to_worker_batch_delta",
                unit="count",
                direction="lower_is_better",
            ),
        ),
    )

    metrics = _probe_command_json(probe=probe, repo_root=REPO_ROOT)

    assert metrics["status_warning"] == 1.0
    assert metrics["failure_count"] == 0.0
    assert metrics["scheduler_admission_cohort_size"] == 2.0
    assert metrics["scheduler_continuous_batch_size"] == 2.0
    assert metrics["worker_decode_batch_size"] == 1.0
    assert metrics["worker_model_eval_batch_size"] == 1.0
    assert metrics["worker_max_model_step_batch_size"] == 1.0
    assert metrics["worker_per_batch_output_tokens_per_second"] == 8.0
    assert metrics["scheduler_to_worker_batch_delta"] == 1.0


def test_same_cohort_batching_probe_registry_command_has_base_fallback(tmp_path: Path) -> None:
    registry_probe = next(
        probe
        for probe in load_probe_registry(REGISTRY_PATH)
        if probe.probe_id == "same-cohort-batching-probe-evidence"
    )

    metrics = _probe_command_json(probe=registry_probe, repo_root=tmp_path)

    assert metrics == {
        "failure_count": 0.0,
        "linked_request_count": 0.0,
        "scheduler_admission_active_cohorts": 0.0,
        "scheduler_admission_cohort_size": 0.0,
        "scheduler_active_cohorts": 0.0,
        "scheduler_continuous_batch_size": 0.0,
        "scheduler_to_worker_batch_delta": 0.0,
        "status_failed": 0.0,
        "status_passed": 0.0,
        "status_warning": 1.0,
        "warning_count": 1.0,
        "worker_decode_batch_observation_count": 0.0,
        "worker_decode_batch_size": 0.0,
        "worker_decode_loop_iterations": 0.0,
        "worker_model_eval_batch_size": 0.0,
        "worker_max_model_step_batch_size": 0.0,
        "worker_per_batch_output_token_count": 0.0,
        "worker_per_batch_output_tokens_per_second": 0.0,
    }


def test_integration_swift_binary_resolution_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_SWIFT_BINARY_RESOLUTION_TRIPLES", "8")
    monkeypatch.setenv("MELIX_SWIFT_BINARY_RESOLUTION_SAMPLES", "1")
    monkeypatch.setenv("MELIX_REMOVE_TREE_DIRECTORIES", "4")
    monkeypatch.setenv("MELIX_REMOVE_TREE_FILES_PER_DIRECTORY", "1")
    monkeypatch.setenv("MELIX_REMOVE_TREE_SAMPLES", "1")

    runpy.run_path(
        str(REPO_ROOT / "scripts/integration_swift_binary_resolution_probe.py"),
        run_name="__main__",
    )

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["candidate_count"] == 9
    assert metrics["elapsed_ms_mean"] >= 0
    assert metrics["legacy_elapsed_ms_mean"] >= 0
    assert "delta_ms_mean" in metrics
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["remove_tree_directories"] == 4
    assert metrics["remove_tree_elapsed_ms_mean"] >= 0
    assert metrics["remove_tree_legacy_elapsed_ms_mean"] >= 0
    assert "remove_tree_delta_ms_mean" in metrics


def test_integration_remove_tree_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_REMOVE_TREE_DIRECTORIES", "4")
    monkeypatch.setenv("MELIX_REMOVE_TREE_FILES_PER_DIRECTORY", "1")
    monkeypatch.setenv("MELIX_REMOVE_TREE_SAMPLES", "1")

    runpy.run_path(
        str(REPO_ROOT / "scripts/integration_remove_tree_probe.py"),
        run_name="__main__",
    )

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["remove_tree_directories"] == 4
    assert metrics["remove_tree_files_per_directory"] == 1
    assert metrics["remove_tree_elapsed_ms_mean"] >= 0
    assert metrics["remove_tree_legacy_elapsed_ms_mean"] >= 0
    assert "remove_tree_peak_bytes_delta_mean" in metrics


def test_scope_report_selects_mlx_text_stop_kwarg_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/runtime/mlx_text_runtime.py"],
    )

    assert scope["selected_count"] == 2
    assert _selected_probe_ids(scope) == [
        "mlx-text-stop-kwarg-signature-cache",
        "mlx-text-stop-filter-prefix-cache",
    ]


def test_mlx_text_stop_filter_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_MLX_TEXT_STOP_FILTER_SAMPLES", "1")
    monkeypatch.setenv("MELIX_MLX_TEXT_STOP_FILTER_EVENTS", "8")

    runpy.run_path(
        str(REPO_ROOT / "scripts/mlx_text_stop_filter_probe.py"),
        run_name="__main__",
    )

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["prefix_length_computations_mean"] == 1.0
    assert metrics["token_event_count"] == 8.0
    assert metrics["stop_sequence_count"] == 5.0


def test_scope_report_selects_dataset_registry_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/dataset_registry/catalog.py"],
    )

    assert scope["selected_count"] == len(DATASET_REGISTRY_SELECTED_PROBE_IDS)
    assert _selected_probe_ids(scope) == DATASET_REGISTRY_SELECTED_PROBE_IDS


def test_scope_report_selects_mlx_audio_wav_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/runtime/mlx_audio_runtime.py"],
    )

    assert scope["selected_count"] == len(MLX_AUDIO_RUNTIME_SELECTED_PROBE_IDS)
    assert _selected_probe_ids(scope) == MLX_AUDIO_RUNTIME_SELECTED_PROBE_IDS
    assert "mlx-audio-wav-streaming-pcm" in _selected_probe_ids(scope)


def test_scope_report_selects_mlx_audio_signature_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/runtime/mlx_audio_runtime.py"],
    )

    assert scope["selected_count"] == len(MLX_AUDIO_RUNTIME_SELECTED_PROBE_IDS)
    assert _selected_probe_ids(scope) == MLX_AUDIO_RUNTIME_SELECTED_PROBE_IDS
    assert "mlx-audio-generate-signature-cache" in _selected_probe_ids(scope)


def test_scope_report_selects_video_preprocessing_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/runtime/video_preprocessing.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "video-preprocessing-uri-byte-length-reuse"


def test_scope_report_selects_training_config_target_module_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/model_ops/training_config.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "training-config-target-module-cache"


def test_training_config_target_modules_probe_script_smoke(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_TRAINING_CONFIG_TARGET_MODULE_SAMPLES", "1")
    monkeypatch.setenv("MELIX_TRAINING_CONFIG_TARGET_MODULE_ITERATIONS", "3")

    runpy.run_path(
        str(REPO_ROOT / "scripts/training_config_target_modules_probe.py"),
        run_name="__main__",
    )

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["checksum"] == 54.0
    assert metrics["iteration_count"] == 3.0
    assert metrics["case_count"] == 4.0


def test_scope_report_selects_lora_experiment_run_dir_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/productization/lora_experiment_store.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "lora-experiment-run-dir-name-scan"


def test_lora_experiment_run_dir_scan_probe_script_smoke(capsys: pytest.CaptureFixture[str]) -> None:
    runpy.run_path(
        str(REPO_ROOT / "scripts/lora_experiment_run_dir_scan_probe.py"),
        run_name="__main__",
    )

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["run_dir_count"] == 8000
    assert metrics["iteration_count"] == 24
    assert metrics["sample_count"] == 5
    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["path_attr_reads_mean"] == 0.0


def test_scope_report_selects_mlx_audio_speech_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/runtime/mlx_audio_runtime.py"],
    )

    assert scope["selected_count"] == len(MLX_AUDIO_RUNTIME_SELECTED_PROBE_IDS)
    assert _selected_probe_ids(scope) == MLX_AUDIO_RUNTIME_SELECTED_PROBE_IDS
    assert "mlx-audio-speech-signature-cache" in _selected_probe_ids(scope)


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

    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert scope["selected_count"] == 3
    assert probe_ids == {
        "training-dataset-token-percentiles-single-sort",
        "training-dataset-validation-split-nsmallest",
        "training-dataset-validation-sample-limit",
    }


def test_scope_report_selects_training_dataset_chunker_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=[
            "services/mlx-worker-python/worker/model_ops/training_dataset_chunker.py"
        ],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "training-dataset-chunker-top-level-base-copy"


def test_scope_report_selects_response_only_boundary_slots_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=[
            "services/mlx-worker-python/worker/model_ops/response_only_boundary.py"
        ],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "response-only-boundary-slotted-records"


def test_response_only_boundary_slots_probe_script_emits_metrics() -> None:
    probe = next(
        probe
        for probe in load_probe_registry(REGISTRY_PATH)
        if probe.probe_id == "response-only-boundary-slotted-records"
    )

    metrics = _probe_command_json(probe=probe, repo_root=REPO_ROOT)

    assert metrics["construction_elapsed_ms_mean"] > 0
    assert metrics["aggregation_elapsed_ms_mean"] > 0
    assert metrics["instance_dict_count_mean"] == 0.0
    assert metrics["boundary_count"] == 50000.0


def test_scope_report_selects_quantization_qat_source_scan_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/model_ops/quantization_pipeline.py"],
    )

    probe_ids = _selected_probe_ids(scope)
    assert "quantization-qat-source-scan-scandir" in probe_ids
    assert "quantization-index-shard-min-single-pass" in probe_ids


def test_scope_report_selects_quantization_gate_manifest_event_streaming_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/productization/quantization_gates.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "quantization-gate-manifest-event-streaming"


def test_quantization_gate_manifest_event_streaming_probe_script_emits_metrics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    runpy.run_path(
        str(REPO_ROOT / "scripts/quantization_gate_manifest_event_streaming_probe.py"),
        run_name="__main__",
    )

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["events_consumed_mean"] == 12.0
    assert metrics["profile_count"] == 6.0


def test_scope_report_selects_startup_signals_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/productization/startup_signals.py"],
    )

    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert scope["selected_count"] == 2
    assert probe_ids == {
        "startup-signals-lazy-worker-log-excerpts",
        "startup-signals-version-compare-single-pass",
    }


def test_startup_signals_version_probe_script_emits_metrics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    runpy.run_path(
        str(REPO_ROOT / "scripts/startup_signals_version_probe.py"),
        run_name="__main__",
    )

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["pair_count"] == 12000.0
    assert metrics["sample_count"] == 7.0
    assert metrics["update_result_elapsed_ms_mean"] > 0
    assert metrics["update_result_iterations"] == 25000.0
    assert metrics["update_result_available_count"] == 12500.0


def test_scope_report_selects_release_gates_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/productization/release_gates.py"],
    )

    assert scope["selected_count"] == 2
    assert _selected_probe_ids(scope) == [
        "gemma-e4b-profile-release-gate",
        "release-gates-m9-failure-count-single-pass",
    ]


def test_scope_report_selects_gemma_e4b_profile_gate_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/productization/gemma_e4b_profile_gate.py"],
    )

    assert scope["selected_count"] == 1
    assert _selected_probe_ids(scope) == ["gemma-e4b-profile-release-gate"]


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
    assert scope["selected_count"] == 5
    assert probe_ids == {
        "evaluation-answer-normalization-fast-path",
        "evaluation-dialogue-diagnostics-top-k",
        "evaluation-job-id-high-water-mark",
        "evaluation-latency-percentile-vector-reuse",
        "evaluation-sample-probe-aggregation",
    }


def test_evaluation_probe_commands_cover_agentic_trajectory_execution() -> None:
    trajectory_tests = (
        (
            "services/mlx-worker-python/tests/test_evaluation_core.py::"
            "test_run_local_suite_persists_agentic_tool_evidence"
        ),
        (
            "services/mlx-worker-python/tests/test_evaluation_core.py::"
            "test_run_local_suite_writes_agentic_judge_prompt_snapshot_and_audit"
        ),
        (
            "services/mlx-worker-python/tests/test_evaluation_core.py::"
            "test_agentic_judge_prompt_snapshot_rejects_hidden_gold_context"
        ),
        (
            "services/mlx-worker-python/tests/test_evaluation_core.py::"
            "test_agentic_judge_payload_no_leak_validator_rejects_forbidden_keys"
        ),
        (
            "services/mlx-worker-python/tests/test_evaluation_core.py::"
            "test_agentic_judge_payload_no_leak_validator_allows_explicit_answer_values"
        ),
        (
            "services/mlx-worker-python/tests/test_evaluation_core.py::"
            "test_agentic_judge_payload_no_leak_validator_rejects_extra_payload_fields"
        ),
        (
            "services/mlx-worker-python/tests/test_evaluation_core.py::"
            "test_run_local_suite_returns_agentic_judge_artifacts_without_jobs_root"
        ),
        (
            "services/mlx-worker-python/tests/test_evaluation_core.py::"
            "test_run_local_suite_injects_agentic_tool_trace_before_scoring"
        ),
    )
    probe_ids = {
        "evaluation-answer-normalization-fast-path",
        "evaluation-compare-target-lookup-early-stop",
        "evaluation-dialogue-diagnostics-top-k",
        "evaluation-job-id-high-water-mark",
        "evaluation-latency-percentile-vector-reuse",
        "evaluation-sample-probe-aggregation",
    }

    probes = {
        probe.probe_id: probe
        for probe in load_probe_registry(REGISTRY_PATH)
        if probe.probe_id in probe_ids
    }

    assert set(probes) == probe_ids
    for probe in probes.values():
        for trajectory_test in trajectory_tests:
            assert trajectory_test in probe.test_command
            assert trajectory_test in probe.coverage_command


def test_evaluation_answer_normalization_probe_command_emits_metrics() -> None:
    probe = next(
        probe
        for probe in load_probe_registry(REGISTRY_PATH)
        if probe.probe_id == "evaluation-answer-normalization-fast-path"
    )

    metrics = _probe_command_json(probe=probe, repo_root=REPO_ROOT)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["numeric_extract_calls_mean"] == 0.0
    assert metrics["option_extract_calls_mean"] == 0.0
    assert metrics["answer_count"] == 3000.0
    assert metrics["free_text_answer_count"] == 2400.0
    assert metrics["normalization_checksum"] > 0


def test_evaluation_compare_target_lookup_early_stop_probe_batches_tiny_lookup() -> None:
    probe = next(
        probe
        for probe in load_probe_registry(REGISTRY_PATH)
        if probe.probe_id == "evaluation-compare-target-lookup-early-stop"
    )

    metrics = _probe_command_json(probe=probe, repo_root=REPO_ROOT)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["get_loaded_model_calls_mean"] == 12.0
    assert metrics["loaded_handle_count"] == 40000.0
    assert metrics["iteration_count"] == 400.0
    assert metrics["sample_count"] == 7.0
    assert metrics["checksum"] == 5600.0


def test_scope_report_selects_code_eval_stdio_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/engine/code_eval_runner.py"],
    )

    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert scope["selected_count"] == 6
    assert probe_ids == {
        "code-eval-code-block-last-match-streaming",
        "code-eval-payload-json-bytes",
        "code-eval-stdio-tail-single-stat",
        "code-eval-runner-script-cache",
        "code-eval-count-tests-line-scan",
        "code-eval-test-count-nonblank-streaming",
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


def test_evaluation_store_probe_commands_cover_extra_artifact_paths() -> None:
    artifact_test = (
        "services/mlx-worker-python/tests/test_evaluation_store.py::"
        "test_persist_result_includes_extra_artifact_paths_in_evidence"
    )
    probe_ids = {
        "evaluation-store-compare-summary-csv-streaming",
        "evaluation-store-samples-csv-streaming",
    }
    probes = {
        probe.probe_id: probe
        for probe in load_probe_registry(REGISTRY_PATH)
        if probe.probe_id in probe_ids
    }

    assert set(probes) == probe_ids
    for probe in probes.values():
        assert artifact_test in probe.test_command
        assert artifact_test in probe.coverage_command


def test_scope_report_selects_evaluation_compare_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/productization/evaluation_compare.py"],
    )

    assert scope["selected_count"] == 2
    assert {probe["id"] for probe in scope["selected_probes"]} == {
        "evaluation-compare-target-lookup-early-stop",
        "evaluation-compare-target-lookup-short-circuit",
    }


def test_evaluation_compare_target_lookup_probe_script_emits_metrics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    runpy.run_path(
        str(REPO_ROOT / "scripts/evaluation_compare_target_lookup_probe.py"),
        run_name="__main__",
    )

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["get_loaded_model_calls_mean"] == 3.0
    assert metrics["loaded_model_count"] == 10000.0
    assert metrics["target_count"] == 3.0
    assert metrics["checksum"] == 6000.0


def test_scope_report_selects_evaluation_final_result_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/productization/evaluation_final_result.py"],
    )

    assert scope["selected_count"] == 3
    assert {probe["id"] for probe in scope["selected_probes"]} == {
        "evaluation-final-result-materialization-streaming",
        "evaluation-final-result-json-typed-score-aggregate",
        "evaluation-final-result-text-fallback-tail-scan",
    }


def test_evaluation_text_fallback_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluation_text_fallback_probe.py",
            "--paragraphs",
            "20",
            "--iterations",
            "3",
            "--samples",
            "2",
        ],
    )

    runpy.run_path(str(REPO_ROOT / "scripts/evaluation_text_fallback_probe.py"), run_name="__main__")

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["legacy_elapsed_ms_mean"] > 0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["checksum"] == 66.0
    assert metrics["paragraph_count"] == 21.0


def test_evaluation_text_fallback_derived_delta_metrics_are_informational() -> None:
    probe = next(
        probe
        for probe in load_probe_registry(REGISTRY_PATH)
        if probe.probe_id == "evaluation-final-result-text-fallback-tail-scan"
    )
    metric_directions = {metric.key: metric.direction for metric in probe.metrics}

    assert metric_directions["delta_ms_mean"] == "informational"
    assert metric_directions["peak_bytes_delta_mean"] == "informational"


def test_evaluation_json_typed_score_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluation_json_typed_score_probe.py",
            "--keys",
            "40",
            "--iterations",
            "3",
            "--samples",
            "2",
        ],
    )

    runpy.run_path(str(REPO_ROOT / "scripts/evaluation_json_typed_score_probe.py"), run_name="__main__")

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["score_checksum"] == pytest.approx(2.625)
    assert metrics["key_count"] == 40.0
    assert metrics["iteration_count"] == 3.0


def test_dispatch_probe_impl_supports_evaluation_final_result_probe() -> None:
    probe = next(
        probe
        for probe in load_probe_registry(REGISTRY_PATH)
        if probe.probe_id == "evaluation-final-result-materialization-streaming"
    )

    metrics = _dispatch_probe_impl(probe=probe, repo_root=REPO_ROOT)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["read_rows_calls_mean"] == 0.0
    assert metrics["sample_count"] == 15000.0
    assert metrics["cache_hit_count"] == 5.0



def test_scope_report_selects_multimodal_fast_path_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/runtime/multimodal_fast_paths.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "multimodal-fast-path-signature-top-level-key-cache"


def test_scope_report_selects_multimodal_preprocessing_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/runtime/multimodal_preprocessing.py"],
    )

    assert scope["selected_count"] == 2
    assert {probe["id"] for probe in scope["selected_probes"]} == {
        "multimodal-preprocessing-local-uri-parse-elision",
        "multimodal-preprocessing-image-uri-single-parse",
    }


def test_scope_report_selects_dataset_registry_preview_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/dataset_registry/catalog.py"],
    )

    assert scope["selected_count"] == 3
    assert {probe["id"] for probe in scope["selected_probes"]} == {
        "dataset-registry-limited-read-streaming",
        "dataset-registry-snapshot-inference-single-pass",
        "dataset-registry-preview-limit-short-circuit",
    }


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

    selected_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert scope["selected_count"] == 2
    assert selected_ids == {
        "statistical-evidence-bootstrap-single-sort",
        "statistical-evidence-category-breakdown-single-pass",
    }


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
    assert scope["selected_count"] == 3
    assert scope["force_all"] is False
    assert selected_ids == {
        "changed-scope-coverage-empty-path-short-circuit",
        "changed-scope-coverage-measured-set-filter",
        "changed-scope-coverage-diff-parser",
    }


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


def test_scope_report_selects_mlx_audio_local_uri_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/runtime/mlx_audio_runtime.py"],
    )

    assert scope["selected_count"] == len(MLX_AUDIO_RUNTIME_SELECTED_PROBE_IDS)
    assert _selected_probe_ids(scope) == MLX_AUDIO_RUNTIME_SELECTED_PROBE_IDS
    assert "mlx-audio-local-uri-zero-copy-preprocess" in _selected_probe_ids(scope)


def test_scope_report_selects_macos_app_bundle_probes() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/productization/macos_app_bundle.py"],
    )

    assert scope["selected_count"] == 2
    assert _selected_probe_ids(scope) == [
        "macos-app-resource-bundle-scandir",
        "macos-app-native-binary-scandir",
    ]


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
    coverage_commands = " ".join(str(probe["coverage_command"]) for probe in scope["selected_probes"])
    assert "test_mlx_vlm_runtime_uses_generate_step_for_mtp_when_available" in coverage_commands
    assert "test_mtp_drafter_acceptance_stats_ignore_unusable_accept_lens" in coverage_commands


def test_scope_report_selects_deterministic_vlm_completion_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/runtime/deterministic_vlm_runtime.py"],
    )

    assert scope["selected_count"] == 1
    assert [probe["id"] for probe in scope["selected_probes"]] == [
        "deterministic-vlm-completion-token-scan"
    ]


def test_scope_report_selects_shared_token_counting_probes() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/runtime/token_counting.py"],
    )

    assert [probe["id"] for probe in scope["selected_probes"]] == [
        "deterministic-ocr-token-count-scan",
        "deterministic-vlm-completion-token-scan",
        "vision-family-prompt-token-count-scan",
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
    assert metrics["dimensions"] == 4097.0


def test_scope_report_selects_deterministic_image_edit_digest_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/runtime/deterministic_image_generation_runtime.py"],
    )

    assert scope["selected_count"] == 2
    assert [probe["id"] for probe in scope["selected_probes"]] == [
        "deterministic-image-edit-digest-reuse",
        "deterministic-image-output-byte-accounting",
    ]


def test_deterministic_image_edit_digest_probe_script_emits_metrics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    runpy.run_path(
        str(REPO_ROOT / "scripts/deterministic_image_edit_digest_probe.py"),
        run_name="__main__",
    )

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 5.0
    assert metrics["image_count"] == 8.0
    assert metrics["digest_calls_mean"] == 2.0
    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["payload_checksum"] > 0


def test_deterministic_image_output_bytes_probe_script_emits_metrics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    runpy.run_path(
        str(REPO_ROOT / "scripts/deterministic_image_output_bytes_probe.py"),
        run_name="__main__",
    )

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 5.0
    assert metrics["generated_image_count"] == 96.0
    assert metrics["edit_image_count"] == 96.0
    assert metrics["output_byte_scan_calls_mean"] == 0.0
    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["generated_output_bytes"] > 0
    assert metrics["edit_output_bytes"] > 0
    assert metrics["payload_checksum"] > 0

def test_scope_report_selects_rerank_core_top_k_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/engine/rerank_core.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "rerank-core-top-k-heap-selection"


def test_rerank_top_k_probe_script_emits_top_k_one_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_RERANK_TOP_K_PROBE_DOCUMENTS", "64")
    monkeypatch.setenv("MELIX_RERANK_TOP_K_PROBE_ITERATIONS", "2")
    monkeypatch.setenv("MELIX_RERANK_TOP_K_PROBE_SAMPLES", "1")
    monkeypatch.setenv("MELIX_RERANK_REQUEST_PROBE_DOCUMENTS", "16")
    monkeypatch.setenv("MELIX_RERANK_REQUEST_PROBE_ITERATIONS", "3")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(
            str(REPO_ROOT / "scripts/rerank_top_k_probe.py"),
            run_name="__main__",
        )

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["document_count"] == 64.0
    assert metrics["iteration_count"] == 2.0
    assert metrics["sample_count"] == 1.0
    assert metrics["top_k"] == 1.0
    assert metrics["result_count"] == 1.0
    assert metrics["elapsed_ms_mean"] >= 0
    assert metrics["request_document_count"] == 16.0
    assert metrics["request_iteration_count"] == 3.0
    assert metrics["request_document_identity_hits"] == 3.0
    assert metrics["request_document_iterations"] == 3.0
    assert metrics["request_score_checksum"] == 45.0


def test_scope_report_selects_deterministic_embedding_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/runtime/deterministic_embedding_runtime.py"],
    )

    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert scope["selected_count"] == 2
    assert probe_ids == {
        "deterministic-embedding-duplicate-input-cache",
        "embedding-core-inputs-view",
    }


def test_scope_report_selects_embedding_core_inputs_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/engine/embedding_core.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "embedding-core-inputs-view"


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


def test_scope_report_selects_bench_report_probe_for_telemetry_fixture() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/tests/telemetry_fixtures.py"],
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


def test_scope_report_selects_maintenance_prompt_shape_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/engine/maintenance_core.py"],
    )

    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert "maintenance-prompt-shape-vector-repeat" in probe_ids


def test_maintenance_prompt_shape_probe_inline_fallback_is_base_compatible() -> None:
    probes = load_probe_registry(REGISTRY_PATH)
    probe = next(
        candidate
        for candidate in probes
        if candidate.probe_id == "maintenance-prompt-shape-vector-repeat"
    )

    assert "_prompt_token_count" in probe.probe_command
    assert 'getattr(MaintenanceCore, "_benchmark_prompt_token_count", None)' in probe.probe_command
    assert 'getattr(MaintenanceCore, "_benchmark_context_lengths", None)' in probe.probe_command
    assert "MaintenanceCore._benchmark_prompt_token_count(plain_prompt)" not in probe.probe_command
    assert "MaintenanceCore._benchmark_context_lengths(suite=suite, parameters={})" not in probe.probe_command


def test_maintenance_prompt_shape_probe_is_importable_without_running() -> None:
    probe_script = runpy.run_path(str(REPO_ROOT / "scripts/maintenance_prompt_shape_probe.py"))

    assert callable(probe_script["main"])
    assert "elapsed_samples" not in probe_script


def test_maintenance_prompt_shape_probe_validates_invariants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe_script = runpy.run_path(str(REPO_ROOT / "scripts/maintenance_prompt_shape_probe.py"))
    main = probe_script["main"]
    probe_globals = main.__globals__
    maintenance_core = probe_script["MaintenanceCore"]

    monkeypatch.setitem(probe_globals, "contexts", (2,))
    monkeypatch.setitem(probe_globals, "sample_count", 1)
    monkeypatch.setitem(probe_globals, "iteration_count", 1)
    monkeypatch.setitem(probe_globals, "plain_iteration_count", 1)
    monkeypatch.setitem(probe_globals, "plain_prompt", "one two")

    monkeypatch.setattr(
        maintenance_core,
        "_shape_benchmark_prompt",
        staticmethod(lambda prompt, *, context_length: "one"),
    )
    with pytest.raises(SystemExit, match="unexpected token count"):
        main()

    monkeypatch.setattr(
        maintenance_core,
        "_shape_benchmark_prompt",
        staticmethod(lambda prompt, *, context_length: "one two"),
    )
    monkeypatch.setattr(
        maintenance_core,
        "_benchmark_prompt_token_count",
        staticmethod(lambda prompt: 3),
    )
    with pytest.raises(SystemExit, match="unexpected plain prompt token count"):
        main()

    monkeypatch.setattr(
        maintenance_core,
        "_benchmark_prompt_token_count",
        staticmethod(lambda prompt: 4096),
    )
    monkeypatch.setitem(probe_globals, "_default_context_length", lambda suite: 7)
    with pytest.raises(SystemExit, match="unexpected default context length"):
        main()


def test_scope_report_selects_maintenance_parameter_normalization_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/engine/maintenance_core.py"],
    )

    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert "maintenance-benchmark-parameter-normalization-single-convert" in probe_ids


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


def test_scope_report_selects_melix_metrics_snapshot_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["scripts/melix_metrics_snapshot.py"],
    )

    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert "melix-metrics-snapshot-runtime-scandir" in probe_ids


def test_scope_report_selects_dev_up_mlx_metal_dist_info_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["scripts/dev_up.py"],
    )

    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert "dev-up-mlx-metal-dist-info-scandir" in probe_ids


def test_scope_report_selects_registry_cache_probe(tmp_path: Path) -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/productization/pr_scoped_performance.py"],
    )

    probe_ids = {probe["id"] for probe in scope["selected_probes"]}
    assert "pr-scoped-performance-registry-cache" in probe_ids

    registry_path = tmp_path / "registry.json"
    registry_payload = []
    for probe_id, watch_globs in (
        ("alpha", ["src/a.py"]),
        ("beta", ["src/*.py"]),
        ("gamma", ["src/c.py"]),
    ):
        registry_payload.append(
            {
                "id": probe_id,
                "name": probe_id.title(),
                "watch_globs": watch_globs,
                "test_command": "true",
                "coverage_command": "true",
                "probe_impl": "command_json",
                "probe_command": "python3 -c 'print({})'",
                "metrics": [{"key": "elapsed_ms_mean", "direction": "lower_is_better"}],
            }
        )
    registry_path.write_text(json.dumps(registry_payload), encoding="utf-8")

    sparse_scope = build_scope_report(
        registry_path=registry_path,
        changed_files=["src/c.py", "src/a.py", "src/b.py", "other.py"],
    )

    loaded_probes = load_probe_registry(registry_path)
    assert not hasattr(loaded_probes[0], "__dict__")
    assert not hasattr(loaded_probes[0].metrics[0], "__dict__")
    assert loaded_probes[0].to_scope_dict()["metrics"] == [
        {
            "key": "elapsed_ms_mean",
            "unit": "value",
            "direction": "lower_is_better",
            "warn_pct": 5.0,
        }
    ]

    assert sparse_scope["matched_probe_ids"] == ["alpha", "beta", "gamma"]
    assert [probe["id"] for probe in sparse_scope["selected_probes"]] == ["alpha", "beta", "gamma"]
    assert sparse_scope["selected_count"] == 3
    coverage_paths_by_probe = {
        str(probe["id"]): probe["coverage_paths"]
        for probe in sparse_scope["selected_probes"]
    }
    assert coverage_paths_by_probe == {
        "alpha": ["src/a.py"],
        "beta": ["src/a.py", "src/b.py", "src/c.py"],
        "gamma": ["src/c.py"],
    }


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


def test_changed_paths_force_all_wildcards_short_circuits_on_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    match_calls: list[str] = []

    monkeypatch.setattr(
        pr_scoped_performance_module,
        "_force_all_wildcard_matchers",
        lambda: (("scripts/", re.compile(r"scripts/pr_scoped_performance_.*\.py")),),
    )

    def tracked_match(path: str, matchers: tuple[tuple[str, re.Pattern[str]], ...]) -> bool:
        match_calls.append(path)
        return path.startswith("scripts/pr_scoped_performance_")

    monkeypatch.setattr(pr_scoped_performance_module, "_matches_any_compiled_glob", tracked_match)

    assert (
        pr_scoped_performance_module._changed_paths_match_force_all_wildcards(
            ["scripts/pr_scoped_performance_report.py", "docs/late.md"]  # type: ignore[arg-type]
        )
        is True
    )
    assert match_calls == ["scripts/pr_scoped_performance_report.py"]


def test_matches_any_glob_uses_explicit_short_circuit(monkeypatch: pytest.MonkeyPatch) -> None:
    glob_calls: list[str] = []

    def tracked_match(path: str, glob: str) -> bool:
        glob_calls.append(glob)
        return glob == "services/*.py"

    monkeypatch.setattr(pr_scoped_performance_module, "_glob_matches_path", tracked_match)

    assert _matches_any_glob(
        "services/mlx-worker-python/worker/productization/pr_scoped_performance.py",
        ("services/*.py", "docs/*.md"),
    ) is True
    assert glob_calls == ["services/*.py"]


def test_coverage_paths_for_probe_uses_explicit_glob_matcher(monkeypatch: pytest.MonkeyPatch) -> None:
    glob_calls: list[str] = []
    probe = ProbeDefinition(
        probe_id="alpha",
        name="Alpha",
        runner="ubuntu-latest",
        watch_globs=("services/*.py", "docs/*.md"),
        test_command="true",
        coverage_command="true",
        probe_impl="benchmark_evaluation_report",
        probe_command="",
        metrics=(MetricDefinition(key="elapsed_ms_mean", unit="ms", direction="lower_is_better"),),
    )

    def tracked_match(path: str, globs: tuple[str, ...]) -> bool:
        glob_calls.extend(globs)
        return path.startswith("services/")

    monkeypatch.setattr(pr_scoped_performance_module, "_matches_any_glob", tracked_match)

    assert coverage_paths_for_probe(probe=probe, changed_files=["services/a.py"]) == ("services/a.py",)
    assert glob_calls == ["services/*.py", "docs/*.md"]


def test_scope_report_empty_direct_paths_skips_probe_matching(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_probe_match(
        changed_paths: set[str],
        probes: tuple[ProbeDefinition, ...],
    ) -> frozenset[int]:  # pragma: no cover - sentinel
        _ = (changed_paths, probes)
        raise AssertionError("empty direct changed paths should not scan probe watch globs")

    monkeypatch.setattr(pr_scoped_performance_module, "_match_probe_indexes", fail_probe_match)

    scope = build_scope_report(registry_path=REGISTRY_PATH, changed_files=[])

    assert scope["force_all"] is False
    assert scope["selected_count"] == 0
    assert scope["selected_probes"] == []
    assert scope["matched_probe_ids"] == []

    assert _coverage_paths_by_probe_id(changed_paths=(), probes=()) == {}


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
    assert (
        [probe["id"] for probe in scope["selected_probes"]]
        == SCOPE_MATCHER_SELECTED_PROBE_IDS
    )
    assert scope["selected_count"] == len(SCOPE_MATCHER_SELECTED_PROBE_IDS)
    assert any(probe["coverage_paths"] for probe in scope["selected_probes"])


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
    coverage_paths = _coverage_paths_by_probe_id(
        changed_paths=("shared.py", "services/b.py", "unmatched.py"),
        probes=probes,
    )
    assert coverage_paths == {
        "alpha": ("shared.py",),
        "beta": ("shared.py", "services/b.py"),
        "gamma": ("shared.py",),
    }
    assert _coverage_paths_by_probe_id(
        changed_paths=("shared.py", "services/b.py", "unmatched.py"),
        probes=probes,
        selected_probe_ids=frozenset({"beta"}),
    ) == {"beta": ("shared.py", "services/b.py")}
    assert (
        _coverage_paths_by_probe_id(
            changed_paths=("shared.py", "services/b.py"),
            probes=probes,
            selected_probe_ids=frozenset({"missing"}),
        )
        == {}
    )


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


def test_match_probe_indexes_reuses_cached_frozenset_without_copying() -> None:
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
    )

    first = _match_probe_indexes(changed_paths={"shared.py", "docs/readme.md"}, probes=probes)
    second = _match_probe_indexes(changed_paths=("docs/readme.md", "shared.py"), probes=probes)

    assert first == {0}
    assert first is second
    assert isinstance(first, frozenset)


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


def test_event_extraction_alignment_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_EVENT_ALIGNMENT_PROBE_SIZE", "5")
    monkeypatch.setenv("MELIX_EVENT_ALIGNMENT_PROBE_ACCEPTED_PER_ROW", "2")
    monkeypatch.setenv("MELIX_EVENT_ALIGNMENT_PROBE_ITERATIONS", "2")
    monkeypatch.setenv("MELIX_EVENT_ALIGNMENT_PROBE_SAMPLES", "1")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(REPO_ROOT / "scripts/event_extraction_alignment_probe.py"), run_name="__main__")

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["matrix_size"] == 5.0
    assert metrics["accepted_edges"] == 10.0
    assert metrics["iterations_per_sample"] == 2.0
    assert metrics["sample_count"] == 1.0
    assert metrics["match_count_mean"] > 0
    assert metrics["elapsed_ms_mean"] >= 0
    assert metrics["similarity_pair_count"] == 512.0
    assert metrics["similarity_elapsed_ms_mean"] >= 0
    assert metrics["similarity_checksum"] > 0


def test_event_extraction_semantic_value_group_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_EVENT_SEMANTIC_GROUP_PROBE_COUNTS", "4,5")
    monkeypatch.setenv("MELIX_EVENT_SEMANTIC_GROUP_PROBE_ITERATIONS", "3")
    monkeypatch.setenv("MELIX_EVENT_SEMANTIC_GROUP_PROBE_SAMPLES", "1")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(REPO_ROOT / "scripts/event_extraction_semantic_value_group_probe.py"), run_name="__main__")

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["value_count_max"] == 5.0
    assert metrics["iterations_per_sample"] == 3.0
    assert metrics["sample_count"] == 1.0
    assert metrics["group_count_per_sample"] > 0
    assert metrics["combination_build_calls_mean"] == 0.0
    assert metrics["elapsed_ms_mean"] >= 0


def test_event_extraction_actor_alias_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_EVENT_ACTOR_ALIAS_PROBE_VALUE_COUNT", "6")
    monkeypatch.setenv("MELIX_EVENT_ACTOR_ALIAS_PROBE_ITERATIONS", "3")
    monkeypatch.setenv("MELIX_EVENT_ACTOR_ALIAS_PROBE_SAMPLES", "1")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(REPO_ROOT / "scripts/event_extraction_actor_alias_probe.py"), run_name="__main__")

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["value_count"] == 6.0
    assert metrics["iterations_per_sample"] == 3.0
    assert metrics["sample_count"] == 1.0
    assert metrics["normalize_calls_mean"] == 6.0
    assert metrics["output_length_per_sample"] > 0
    assert metrics["elapsed_ms_mean"] >= 0


def test_event_extraction_response_json_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_EVENT_RESPONSE_JSON_PROBE_EVENT_COUNT", "4")
    monkeypatch.setenv("MELIX_EVENT_RESPONSE_JSON_PROBE_ITERATIONS", "3")
    monkeypatch.setenv("MELIX_EVENT_RESPONSE_JSON_PROBE_SAMPLES", "1")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(REPO_ROOT / "scripts/event_extraction_response_json_probe.py"), run_name="__main__")

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["event_count"] == 4.0
    assert metrics["iterations_per_sample"] == 3.0
    assert metrics["sample_count"] == 1.0
    assert metrics["checksum"] == 12.0
    assert metrics["elapsed_ms_mean"] >= 0
    assert metrics["peak_bytes_mean"] > 0


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


def test_hub_catalog_size_hint_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_HUB_CATALOG_SIZE_HINT_ITERATIONS", "8")
    monkeypatch.setenv("MELIX_HUB_CATALOG_SIZE_HINT_SAMPLES", "1")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(REPO_ROOT / "scripts/hub_catalog_size_hint_probe.py"), run_name="__main__")

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 1.0
    assert metrics["size_hint_calls_mean"] == 2.0
    assert metrics["matched_hint_count"] == 4.0
    assert metrics["payload_compatibility_calls_mean"] == 8.0
    assert metrics["payload_compatibility_matched_count"] == 7.0
    assert metrics["payload_compatibility_elapsed_ms_mean"] >= 0
    assert metrics["elapsed_ms_mean"] >= 0
    assert metrics["peak_bytes_mean"] > 0


def test_hub_catalog_next_cursor_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_HUB_CATALOG_CURSOR_ITERATIONS", "8")
    monkeypatch.setenv("MELIX_HUB_CATALOG_CURSOR_SAMPLES", "1")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(REPO_ROOT / "scripts/hub_catalog_next_cursor_probe.py"), run_name="__main__")

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 1.0
    assert metrics["cursor_parse_calls_mean"] == 8.0
    assert metrics["checksum"] > 0
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
    assert metrics["sorted_calls_mean"] == 0.0
    assert metrics["elapsed_ms_mean"] >= 0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["lower_bound_mean"] <= metrics["upper_bound_mean"]


def test_statistical_evidence_category_breakdown_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_STAT_CATEGORY_ROWS", "18")
    monkeypatch.setenv("MELIX_STAT_CATEGORY_COUNT", "3")
    monkeypatch.setenv("MELIX_STAT_CATEGORY_PROBE_SAMPLES", "1")

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(
            str(REPO_ROOT / "scripts/statistical_evidence_category_breakdown_probe.py"),
            run_name="__main__",
        )

    assert excinfo.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 1.0
    assert metrics["row_count"] == 18.0
    assert metrics["category_count"] == 3.0
    assert metrics["checksum"] > 0
    assert metrics["elapsed_ms_mean"] >= 0
    assert metrics["peak_bytes_mean"] > 0


def test_training_dataset_chunker_top_level_copy_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_CHUNKER_PROBE_SAMPLES", "1")
    monkeypatch.setenv("MELIX_CHUNKER_PROBE_TOP_KEYS", "4")
    monkeypatch.setenv("MELIX_CHUNKER_PROBE_WORDS", "240")
    monkeypatch.setenv("MELIX_CHUNKER_PROBE_CHUNK_SIZE", "60")

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(
            str(REPO_ROOT / "scripts/training_dataset_chunker_top_level_copy_probe.py"),
            run_name="__main__",
        )

    assert excinfo.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 1.0
    assert metrics["top_level_key_count"] == 7.0
    assert metrics["chunk_count"] > 1.0
    assert metrics["elapsed_ms_mean"] >= 0
    assert metrics["peak_bytes_mean"] > 0


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


def test_multimodal_preprocessing_uri_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_PROBE_ITERATIONS", "3")
    monkeypatch.setenv("MELIX_PROBE_SAMPLES", "1")

    runpy.run_path(
        str(REPO_ROOT / "scripts/multimodal_preprocessing_uri_probe.py"),
        run_name="__main__",
    )

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["iteration_count"] == 3.0
    assert metrics["sample_count"] == 1.0
    assert metrics["urlparse_calls_mean"] == 0.0
    assert metrics["read_bytes_calls_mean"] == 3.0
    assert metrics["image_parts_per_iteration"] == 2.0
    assert metrics["elapsed_ms_mean"] >= 0


def test_multimodal_image_uri_parse_probe_script_emits_metrics(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(REPO_ROOT / "scripts/multimodal_image_uri_parse_probe.py"), run_name="__main__")

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 5.0
    assert metrics["prepared_image_count"] == 640.0
    assert metrics["urlparse_calls_mean"] == 0.0
    assert metrics["unquote_calls_mean"] == 0.0
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


def test_embedding_core_inputs_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_EMBEDDING_CORE_INPUTS_ITERATIONS", "2")
    monkeypatch.setenv("MELIX_EMBEDDING_CORE_INPUTS_SAMPLES", "1")
    monkeypatch.setenv("MELIX_EMBEDDING_CORE_INPUTS_COUNT", "8")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(
            str(REPO_ROOT / "scripts/embedding_core_inputs_probe.py"),
            run_name="__main__",
        )

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["input_count"] == 8.0
    assert metrics["iterations"] == 2.0
    assert metrics["runtime_input_is_list"] == 0.0
    assert metrics["runtime_input_is_view"] == 1.0
    assert metrics["elapsed_ms_mean"] >= 0
    assert metrics["peak_bytes_mean"] > 0


def test_stream_assembler_parser_mode_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_STREAM_ASSEMBLER_PARSER_MODE_CHUNKS", "180")
    monkeypatch.setenv("MELIX_STREAM_ASSEMBLER_PARSER_MODE_SAMPLES", "1")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(
            str(REPO_ROOT / "scripts/stream_assembler_parser_mode_probe.py"),
            run_name="__main__",
        )
    assert exc_info.value.code == 0

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 1.0
    assert metrics["chunk_count"] == 180.0
    assert metrics["tool_call_count"] == 2.0
    assert metrics["harmony_channel_count"] == 2.0
    assert metrics["channel_name_calls_mean"] == 2.0
    assert metrics["channel_name_checksum"] > 0.0
    assert metrics["elapsed_ms_mean"] >= 0



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
    assert metrics["partial_suffix_hits"] == 3.0
    assert metrics["prefix_identity_hits"] == 3.0
    assert metrics["elapsed_ms_mean"] >= 0
    assert metrics["partial_suffix_elapsed_ms_mean"] >= 0
    assert metrics["peak_bytes_mean"] > 0


def test_stream_assembler_token_bytes_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_STREAM_ASSEMBLER_TOKEN_BYTES_EVENTS", "8")
    monkeypatch.setenv("MELIX_STREAM_ASSEMBLER_TOKEN_BYTES_SAMPLES", "1")

    runpy.run_path(
        str(REPO_ROOT / "scripts/stream_assembler_token_bytes_probe.py"),
        run_name="__main__",
    )

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 1.0
    assert metrics["token_event_count"] == 8.0
    assert metrics["generated_token_count_mean"] == 8.0
    assert metrics["elapsed_ms_mean"] >= 0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["checksum"] > 0


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
    assert metrics["inspect_signature_calls_mean"] == 1.0
    assert metrics["elapsed_ms_mean"] >= 0


def test_runtime_utils_package_version_probe_script_emits_metrics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(
            str(REPO_ROOT / "scripts/runtime_utils_package_version_probe.py"),
            run_name="__main__",
        )

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 5.0
    assert metrics["iterations_per_sample"] == 60000.0
    assert metrics["package_count"] == 3.0
    assert metrics["metadata_version_calls_mean"] == 3.0
    assert metrics["elapsed_ms_mean"] >= 0


def test_runtime_utils_top_level_weights_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_RUNTIME_UTILS_WEIGHT_FILES", "8")
    monkeypatch.setenv("MELIX_RUNTIME_UTILS_WEIGHT_ITERATIONS", "2")
    monkeypatch.setenv("MELIX_RUNTIME_UTILS_WEIGHT_SAMPLES", "1")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(
            str(REPO_ROOT / "scripts/runtime_utils_top_level_weights_probe.py"),
            run_name="__main__",
        )

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["file_count"] == 8.0
    assert metrics["iterations"] == 2.0
    assert metrics["expected_bytes"] > 0
    assert metrics["checksum"] == metrics["expected_bytes"] * metrics["iterations"]
    assert metrics["elapsed_ms_mean"] >= 0
    assert metrics["peak_bytes_mean"] > 0


def test_mlx_text_stop_kwarg_signature_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_MLX_TEXT_STOP_KWARG_PROBE_ITERATIONS", "12")
    monkeypatch.setenv("MELIX_MLX_TEXT_STOP_KWARG_PROBE_SAMPLES", "1")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(
            str(REPO_ROOT / "scripts/mlx_text_stop_kwarg_signature_probe.py"),
            run_name="__main__",
        )

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 1.0
    assert metrics["iterations_per_sample"] == 12.0
    assert metrics["stream_signature_calls_mean"] == 1.0
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


def test_dataset_registry_split_match_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_DATASET_SPLIT_MATCH_PROBE_FILE_COUNT", "12")
    monkeypatch.setenv("MELIX_DATASET_SPLIT_MATCH_PROBE_SAMPLES", "1")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(
            str(REPO_ROOT / "scripts/dataset_registry_split_match_probe.py"),
            run_name="__main__",
        )

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 1.0
    assert metrics["file_count"] == 12.0
    assert metrics["matched_files_mean"] == 3.0
    assert metrics["path_constructor_calls_mean"] == 0.0
    assert metrics["elapsed_ms_mean"] >= 0
    assert metrics["peak_bytes_mean"] > 0


def test_maintenance_parameter_normalization_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_MAINTENANCE_PARAMETER_PROBE_VALUE_COUNT", "12")
    monkeypatch.setenv("MELIX_MAINTENANCE_PARAMETER_PROBE_ITERATIONS", "2")
    monkeypatch.setenv("MELIX_MAINTENANCE_PARAMETER_PROBE_SAMPLES", "1")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(
            str(REPO_ROOT / "scripts/maintenance_benchmark_parameter_normalization_probe.py"),
            run_name="__main__",
        )

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 1.0
    assert metrics["iteration_count"] == 2.0
    assert metrics["value_count"] == 12.0
    assert metrics["calls_per_value_mean"] == 1.0
    assert metrics["int_conversion_calls_mean"] == 24.0
    assert metrics["string_conversion_calls_mean"] == 24.0
    assert metrics["native_checksum"] > 0.0
    assert metrics["elapsed_ms_mean"] >= 0
    assert metrics["native_elapsed_ms_mean"] >= 0
    assert metrics["peak_bytes_mean"] > 0


def test_mlx_audio_wav_streaming_probe_script_emits_metrics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(
            str(REPO_ROOT / "scripts/mlx_audio_wav_streaming_probe.py"),
            run_name="__main__",
        )

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 240000.0
    assert metrics["wav_bytes"] == 480044.0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["elapsed_ms_mean"] >= 0


def test_mlx_audio_generate_signature_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_MLX_AUDIO_SIGNATURE_PROBE_ITERATIONS", "3")
    monkeypatch.setenv("MELIX_MLX_AUDIO_SIGNATURE_PROBE_SAMPLES", "1")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(
            str(REPO_ROOT / "scripts/mlx_audio_generate_signature_probe.py"),
            run_name="__main__",
        )

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 1.0
    assert metrics["iterations_per_sample"] == 3.0
    assert metrics["signature_calls_mean"] == 0.0
    assert metrics["audio_bytes_total"] > 0
    assert metrics["elapsed_ms_mean"] >= 0


def test_dataset_registry_snapshot_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_DATASET_REGISTRY_PROBE_FILE_COUNT", "3")
    monkeypatch.setenv("MELIX_DATASET_REGISTRY_PROBE_SAMPLES", "1")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(
            str(REPO_ROOT / "scripts/dataset_registry_snapshot_probe.py"),
            run_name="__main__",
        )

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["elapsed_ms_mean"] >= 0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["legacy_inference_helper_calls_mean"] == 0.0
    assert metrics["file_count_mean"] == 4.0


def test_video_preprocessing_uri_probe_script_emits_metrics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(
            str(REPO_ROOT / "scripts/video_preprocessing_uri_probe.py"),
            run_name="__main__",
        )

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 5.0
    assert metrics["iterations_per_sample"] == 50000.0
    assert metrics["byte_length_getattrs_per_call"] == 1.0
    assert metrics["parse_calls_per_call"] == 1.0
    assert metrics["elapsed_ms_mean"] >= 0


def test_quantization_qat_source_scan_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_QAT_SOURCE_SCAN_PROBE_FILES", "4")
    monkeypatch.setenv("MELIX_QAT_SOURCE_SCAN_PROBE_SAMPLES", "1")
    monkeypatch.setenv("MELIX_QAT_SOURCE_STATS_PROBE_BYTES_PER_FILE", "256")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(
            str(REPO_ROOT / "scripts/quantization_qat_source_scan_probe.py"),
            run_name="__main__",
        )

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 1.0
    assert metrics["file_count"] == 4.0
    assert metrics["rglob_calls_mean"] == 0.0
    assert metrics["scandir_calls_mean"] >= 1.0
    assert metrics["source_stats_byte_count"] == 1024.0
    assert metrics["source_stats_elapsed_ms_mean"] >= 0
    assert metrics["source_stats_peak_bytes_mean"] > 0
    assert metrics["elapsed_ms_mean"] >= 0


def test_quantization_index_shard_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_QUANTIZATION_INDEX_SHARD_PROBE_ENTRIES", "6")
    monkeypatch.setenv("MELIX_QUANTIZATION_INDEX_SHARD_PROBE_ITERATIONS", "2")
    monkeypatch.setenv("MELIX_QUANTIZATION_INDEX_SHARD_PROBE_SAMPLES", "1")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(
            str(REPO_ROOT / "scripts/quantization_index_shard_probe.py"),
            run_name="__main__",
        )

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 1.0
    assert metrics["iterations_per_sample"] == 2.0
    assert metrics["weight_map_entries"] == 9.0
    assert metrics["sorted_calls_mean"] == 0.0
    assert metrics["elapsed_ms_mean"] >= 0
    assert metrics["peak_bytes_mean"] > 0


def test_mlx_audio_speech_signature_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_AUDIO_SPEECH_SIGNATURE_PROBE_CALLS", "3")
    monkeypatch.setenv("MELIX_AUDIO_SPEECH_SIGNATURE_PROBE_SAMPLES", "1")

    runpy.run_path(
        str(REPO_ROOT / "scripts/mlx_audio_speech_signature_probe.py"),
        run_name="__main__",
    )

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 1.0
    assert metrics["speak_call_count"] == 3.0
    assert metrics["inspect_signature_calls_mean"] == 0.0
    assert metrics["elapsed_ms_mean"] >= 0
    assert metrics["output_bytes_total"] > 0


def test_dataset_registry_preview_limit_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_DATASET_PREVIEW_PROBE_FILES", "4")
    monkeypatch.setenv("MELIX_DATASET_PREVIEW_PROBE_SIDECARS", "3")
    monkeypatch.setenv("MELIX_DATASET_PREVIEW_PROBE_SAMPLES", "1")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(REPO_ROOT / "scripts/dataset_registry_preview_limit_probe.py"), run_name="__main__")

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["file_count"] == 4.0
    assert metrics["sidecar_count"] == 3.0
    assert metrics["rows_returned"] == 1.0
    assert metrics["zero_limit_rows_returned"] == 0.0
    assert metrics["elapsed_ms_mean"] >= 0
    assert metrics["zero_limit_elapsed_ms_mean"] >= 0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["zero_limit_peak_bytes_mean"] >= 0


def test_release_gates_m9_failure_count_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_RELEASE_GATES_M9_PROBE_SECTIONS", "3")
    monkeypatch.setenv("MELIX_RELEASE_GATES_M9_PROBE_FAILURES", "4")
    monkeypatch.setenv("MELIX_RELEASE_GATES_M9_PROBE_SAMPLES", "1")

    runpy.run_path(
        str(REPO_ROOT / "scripts/release_gates_m9_failure_count_probe.py"),
        run_name="__main__",
    )

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["elapsed_ms_mean"] >= 0
    assert metrics["endswith_checks_mean"] == 0.0
    assert metrics["failure_count_mean"] == 12.0
    assert metrics["section_count"] == 3.0
    assert metrics["failures_per_section"] == 4.0


def test_gemma_e4b_profile_gate_probe_script_emits_metrics() -> None:
    probe = next(
        probe
        for probe in load_probe_registry(REGISTRY_PATH)
        if probe.probe_id == "gemma-e4b-profile-release-gate"
    )

    metrics = _probe_command_json(probe=probe, repo_root=REPO_ROOT)

    assert metrics["release_gate_passed"] == 1.0
    assert metrics["failure_count"] == 0.0
    assert metrics["selected_profile_receipt_passed"] == 1.0
    assert metrics["capability_receipt_supported"] == 1.0
    assert metrics["unsupported_selected_route_count"] == 0.0
    assert metrics["benchmark_threshold_passed"] == 1.0
    assert metrics["elapsed_ms_mean"] > 0.0
    assert metrics["iteration_count"] == 2000.0
    assert metrics["sample_count"] == 5.0


def test_gemma_e4b_profile_gate_probe_script_main_covers_checked_in_file(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    script_path = REPO_ROOT / "scripts" / "gemma_e4b_profile_gate_probe.py"
    spec = importlib.util.spec_from_file_location("gemma_e4b_profile_gate_probe_test", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", ["gemma_e4b_profile_gate_probe.py", "--metrics"])

    assert module.main() == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["release_gate_passed"] == 1.0
    assert metrics["failure_count"] == 0.0

    input_path = tmp_path / "evidence.json"
    input_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.gemma_e4b_profile_gate.v1",
                "artifact_status": "missing",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["gemma_e4b_profile_gate_probe.py", "--input", str(input_path)])

    assert module.main() == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "failed"
    assert report["artifact_status"] == "missing"

    with pytest.raises(ValueError, match="samples must be at least 1"):
        module.collect_metrics(module.default_passing_evidence(), samples=0, iterations=1)
    with pytest.raises(ValueError, match="iterations must be at least 1"):
        module.collect_metrics(module.default_passing_evidence(), samples=1, iterations=0)


def test_gemma_e4b_profile_gate_probe_rejects_non_object_input(tmp_path: Path) -> None:
    script_path = REPO_ROOT / "scripts" / "gemma_e4b_profile_gate_probe.py"
    spec = importlib.util.spec_from_file_location("gemma_e4b_profile_gate_probe_test_input", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    input_path = tmp_path / "bad.json"
    input_path.write_text(json.dumps(["bad"]), encoding="utf-8")

    with pytest.raises(ValueError, match="must be a JSON object"):
        module.load_evidence(input_path)


def test_scope_report_selects_text_family_config_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/runtime/text_family_adapters.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "text-family-config-copy-elision"


def test_text_family_config_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["text_family_config_probe.py"])

    runpy.run_path(str(REPO_ROOT / "scripts/text_family_config_probe.py"), run_name="__main__")

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["config_copy_calls_mean"] == 0.0
    assert metrics["iterations"] == 10_000


def test_registered_probes_expose_focused_commands() -> None:
    replaying_probe_ids = {
        "dataset-registry-limited-read-streaming",
        "dataset-registry-snapshot-inference-single-pass",
        "event-extraction-alignment-accepted-edge-cache",
        "event-extraction-semantic-value-group-cache",
        "event-extraction-group-actor-alias-cache",
        "event-extraction-response-json-fence-trim",
        "hub-catalog-tag-normalization-single-pass",
        "hub-catalog-next-cursor-fast-parse",
        "hub-catalog-size-hint-regex-precompile",
        "integration-swift-binary-resolution-scandir",
        "benchmark-evaluation-report-running-aggregates",
        "stream-assembler-parser-mode-cache",
        "stream-assembler-token-byte-fast-decode",
        "benchmark-export-run-scan-single-pass",
        "benchmark-queue-decoded-record-cache",
        "benchmark-store-matrix-streaming",
        "changed-scope-coverage-empty-path-short-circuit",
        "changed-scope-coverage-measured-set-filter",
        "changed-scope-coverage-diff-parser",
        "closure-audit-probe-source-short-circuit",
        "code-eval-code-block-last-match-streaming",
        "code-eval-payload-json-bytes",
        "code-eval-stdio-tail-single-stat",
        "code-eval-runner-script-cache",
        "code-eval-count-tests-line-scan",
        "code-eval-test-count-nonblank-streaming",
        "deterministic-embedding-duplicate-input-cache",
        "deterministic-embedding-project-digest-allocation",
        "deterministic-ocr-token-count-scan",
        "deterministic-vlm-completion-token-scan",
        "deterministic-image-edit-digest-reuse",
        "deterministic-image-output-byte-accounting",
        "deterministic-rerank-query-context-reuse",
        "rerank-core-top-k-heap-selection",
        "same-cohort-batching-probe-evidence",
        "runtime-utils-kwarg-signature-cache",
        "runtime-utils-package-version-cache",
        "runtime-utils-top-level-weight-streaming",
        "mlx-text-stop-kwarg-signature-cache",
        "mlx-text-stop-filter-prefix-cache",
        "mlx-audio-wav-streaming-pcm",
        "mlx-audio-generate-signature-cache",
        "mlx-audio-speech-signature-cache",
        "video-preprocessing-uri-byte-length-reuse",
        "vision-family-prompt-token-count-scan",
        "probe-policy-noop-overhead",
        "serving-diagnostics-debug-queue-bounds",
        "dev-up-mlx-metal-dist-info-scandir",
        "evaluation-answer-normalization-fast-path",
        "evaluation-dialogue-diagnostics-top-k",
        "evaluation-job-id-high-water-mark",
        "evaluation-dialogue-diagnostics-top-k",
        "evaluation-final-result-materialization-streaming",
        "evaluation-final-result-json-typed-score-aggregate",
        "evaluation-final-result-text-fallback-tail-scan",
        "gemma-e4b-profile-release-gate",
        "evaluation-latency-percentile-vector-reuse",
        "evaluation-sample-probe-aggregation",
        "evaluation-compare-target-lookup-short-circuit",
        "evaluation-store-compare-summary-csv-streaming",
        "evaluation-compare-target-lookup-early-stop",
        "evaluation-store-samples-csv-streaming",
        "engine-generate-usage-token-elision",
        "report-evidence-gate-run-kind-set-membership",
        "embedding-core-inputs-view",
        "job-registry-derived-model-single-pass",
        "job-registry-restore-sort-elision",
        "lora-aux-modules-scandir",
        "lora-experiment-run-dir-name-scan",
        "lora-reward-summary-candidate-minmax",
        "mlx-lm-structured-result-tail-parse",
        "native-mtp-loader-safetensor-scandir",
        "mlx-audio-local-uri-zero-copy-preprocess",
        "mlx-audio-generate-signature-cache",
        "mlx-audio-speech-signature-cache",
        "mlx-vlm-family-config-cache",
        "mlx-vlm-gemma4-weight-presence-single-pass",
        "model-registry-plain-local-manifest-stat-elision",
        "multimodal-fast-path-signature-top-level-key-cache",
        "multimodal-preprocessing-local-uri-parse-elision",
        "multimodal-preprocessing-image-uri-single-parse",
        "macos-app-resource-bundle-scandir",
        "macos-app-native-binary-scandir",
        "package-macos-resolve-fallback-scandir",
        "melix-metrics-snapshot-runtime-scandir",
        "pr-scoped-performance-scope-json-read-bytes",
        "pr-scoped-performance-scope-matcher",
        "quantization-gate-manifest-event-streaming",
        "quantization-qat-source-scan-scandir",
        "quantization-index-shard-min-single-pass",
        "release-gates-m9-failure-count-single-pass",
        "training-config-target-module-cache",
        "training-dataset-token-percentiles-single-sort",
        "training-dataset-validation-split-nsmallest",
        "training-dataset-validation-sample-limit",
        "training-dataset-chunker-top-level-base-copy",
        "trajectory-provenance-copy-elision",
        "trajectory-manifest-json-load",
        "dataset-registry-preview-limit-short-circuit",
        "dataset-version-listing-scandir",
        "dataset-quality-lengths-chain",
        "dataset-source-records-scandir",
        "maintenance-bench-report-readback",
        "maintenance-percentile-vector-reuse",
        "maintenance-prompt-shape-vector-repeat",
        "maintenance-benchmark-parameter-normalization-single-convert",
        "phase8-metrics-closure-audit-reuse",
        "pr-scoped-performance-registry-cache",
        "real-model-support-hf-cache-latest-snapshot",
        "stream-assembler-structural-prefix-cache",
        "swift-cli-json-envelope-encoding",
        "startup-signals-lazy-worker-log-excerpts",
        "startup-signals-version-compare-single-pass",
        "upload-receipt-published-files-scandir",
        "video-preprocessing-uri-byte-length-reuse",
        "download-pipeline-directory-size-single-stat",
        "worker-registry-resident-bytes-accumulator",
        "pr-scoped-performance-report-results-scandir",
        "model-ops-bundle-artifact-byte-accounting",
        "statistical-evidence-bootstrap-single-sort",
        "statistical-evidence-category-breakdown-single-pass",
        "text-family-config-copy-elision",
        "response-only-boundary-slotted-records",
        "tool-registry-schema-bytes-cache",
        "tool-registry-select-name-index-cache",
        "tool-registry-names-snapshot-cache",
        "tool-registry-openai-tools-template-cache",
    }
    registry_probe = None
    maintenance_probe = None
    job_registry_probe = None
    integration_helper_probe = None
    video_preprocessing_probe = None
    gemma4_weight_presence_probe = None
    worker_registry_probe = None
    swift_probe = None
    for probe in load_probe_registry(REGISTRY_PATH):
        assert probe.test_command
        assert probe.coverage_command
        assert probe.probe_command
        assert "uv run --project services/mlx-worker-python bash -lc" not in probe.probe_command
        assert "uv run --project services/mlx-worker-python python " not in probe.probe_command
        assert "then python scripts/" not in probe.probe_command
        assert "else python - <<" not in probe.probe_command
        assert "if false; then python scripts/" not in probe.probe_command
        assert probe.coverage_replays_tests is (probe.probe_id in replaying_probe_ids)
        if probe.probe_id == "model-registry-plain-local-manifest-stat-elision":
            registry_probe = probe
        if probe.probe_id == "maintenance-percentile-vector-reuse":
            maintenance_probe = probe
        if probe.probe_id == "job-registry-derived-model-single-pass":
            job_registry_probe = probe
        if probe.probe_id == "integration-swift-binary-resolution-scandir":
            integration_helper_probe = probe
        if probe.probe_id == "video-preprocessing-uri-byte-length-reuse":
            video_preprocessing_probe = probe
        if probe.probe_id == "mlx-vlm-gemma4-weight-presence-single-pass":
            gemma4_weight_presence_probe = probe
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
    assert "test_has_mlx_signal_config_payload_fast_path_avoids_json_dump" in registry_probe.test_command
    assert "scripts/changed_scope_coverage.py" not in registry_probe.watch_globs
    assert "test_registry_snapshot_reuses_hf_cache_config_payload" in registry_probe.coverage_command
    assert "test_raw_model_spec_loads_config_payload_when_not_supplied" in registry_probe.coverage_command
    assert "test_has_mlx_signal_falls_back_to_config_text_for_empty_supplied_payload" in registry_probe.coverage_command
    assert "test_has_mlx_signal_skips_config_text_fallback_for_nonempty_payload_without_mlx_signal" in registry_probe.coverage_command
    assert "test_metadata_payload_has_mlx_signal_does_not_request_sorted_json" in registry_probe.coverage_command
    assert "test_has_mlx_signal_config_payload_fast_path_avoids_json_dump" in registry_probe.coverage_command
    assert "scripts/changed_scope_coverage.py" in registry_probe.coverage_command

    assert maintenance_probe is not None
    assert "test_measure_vlm_latency_metrics_reuse_single_sorted_total_latency_vector" in maintenance_probe.test_command
    assert "test_image_latency_metrics_reuse_single_sorted_job_latency_vector" in maintenance_probe.test_command
    assert "test_measure_vlm_latency_metrics_reuse_single_sorted_total_latency_vector" in maintenance_probe.coverage_command
    assert "test_image_latency_metrics_reuse_single_sorted_job_latency_vector" in maintenance_probe.coverage_command

    assert job_registry_probe is not None
    job_registry_metrics = {
        metric.key: metric for metric in job_registry_probe.metrics
    }
    assert job_registry_metrics["active_manifest_elapsed_ms_mean"].warn_abs == 0.01
    assert job_registry_metrics["resolve_target_elapsed_ms_mean"].warn_abs == 0.01
    assert job_registry_metrics["manifest_path_elapsed_ms_mean"].warn_abs == 0.01

    assert integration_helper_probe is not None
    integration_helper_metrics = {
        metric.key: metric for metric in integration_helper_probe.metrics
    }
    assert integration_helper_metrics["delta_ms_mean"].warn_pct == 0.0
    assert integration_helper_metrics["delta_ms_mean"].warn_abs == 5.0
    assert integration_helper_metrics["remove_tree_delta_ms_mean"].warn_pct == 0.0
    assert integration_helper_metrics["remove_tree_delta_ms_mean"].warn_abs == 5.0
    assert integration_helper_metrics["remove_tree_peak_bytes_delta_mean"].warn_pct == 0.0
    assert integration_helper_metrics["remove_tree_peak_bytes_delta_mean"].warn_abs == 65536.0

    assert video_preprocessing_probe is not None
    video_preprocessing_metrics = {
        metric.key: metric for metric in video_preprocessing_probe.metrics
    }
    assert video_preprocessing_metrics["elapsed_ms_mean"].warn_abs == 50.0
    assert video_preprocessing_metrics["byte_length_getattrs_per_call"].warn_pct == 0.0
    assert video_preprocessing_metrics["byte_length_getattrs_per_call"].warn_abs == 0.0
    assert video_preprocessing_metrics["parse_calls_per_call"].warn_pct == 0.0
    assert video_preprocessing_metrics["parse_calls_per_call"].warn_abs == 0.0

    assert gemma4_weight_presence_probe is not None
    gemma4_weight_presence_metrics = {
        metric.key: metric for metric in gemma4_weight_presence_probe.metrics
    }
    assert gemma4_weight_presence_metrics["peak_bytes_mean"].warn_pct == 5.0
    assert gemma4_weight_presence_metrics["peak_bytes_mean"].warn_abs == 64.0

    assert swift_probe is not None
    assert "MelixCLIRunnerTests/(" in swift_probe.test_command
    assert "MelixCLITests/MelixCLIRunnerTests" not in swift_probe.test_command
    swift_verification_tests = (
        "jsonV1WrapsCommandResultsInAStableEnvelope",
        "jsonV1ErrorEnvelopesAreMachineReadable",
        "jsonMetricPlaceholdersSanitizeScalarNamesWithoutChangingTokenShape",
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


def test_registered_probe_registry_entries_validate_commands_and_watch_globs() -> None:
    registry_payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    seen_ids: set[str] = set()
    for raw_probe in registry_payload:
        probe_id = raw_probe["id"]
        assert probe_id not in seen_ids
        seen_ids.add(probe_id)
        assert raw_probe.get("watch_globs"), f"{probe_id} must declare changed-file globs"
        assert raw_probe.get("test_command", "").strip(), f"{probe_id} must declare a focused test command"
        coverage_command = str(raw_probe.get("coverage_command", ""))
        assert coverage_command.strip(), f"{probe_id} must declare a coverage command"
        assert "python scripts/changed_scope_coverage.py" not in coverage_command
        if "scripts/changed_scope_coverage.py" in coverage_command:
            assert "python3 scripts/changed_scope_coverage.py" in coverage_command
        assert raw_probe.get("probe_command", "").strip() or raw_probe.get("probe_impl") != "command_json"
        assert raw_probe.get("metrics"), f"{probe_id} must declare metrics"
        for glob in raw_probe.get("watch_globs", []):
            assert str(glob).startswith("/") is False
            assert ".." not in Path(str(glob)).parts

    by_id = {raw_probe["id"]: raw_probe for raw_probe in registry_payload}
    for probe_id in ("probe-policy-noop-overhead", "serving-diagnostics-debug-queue-bounds"):
        watch_globs = by_id[probe_id]["watch_globs"]
        probe_command = by_id[probe_id]["probe_command"]
        assert "scripts/changed_scope_coverage.py" not in watch_globs
        assert "scripts/changed_scope_coverage.py" in by_id[probe_id]["coverage_command"]
        assert "services/mlx-worker-python/tests/test_pr_scoped_performance.py" in watch_globs
        assert "../head/$SCRIPT" in probe_command
        assert "${GITHUB_WORKSPACE:-}/head/$SCRIPT" in probe_command

    probe_policy_metrics = {
        metric["key"]: metric for metric in by_id["probe-policy-noop-overhead"]["metrics"]
    }
    assert probe_policy_metrics["no_op_recorder_overhead_pct"]["direction"] == "informational"
    assert probe_policy_metrics["no_op_policy_check_overhead_pct"]["direction"] == "informational"
    assert probe_policy_metrics["no_op_reason_overhead_pct"]["direction"] == "informational"
    assert probe_policy_metrics["no_op_reason_call_ms_mean"]["direction"] == "lower_is_better"
    assert probe_policy_metrics["threshold_passed"]["direction"] == "higher_is_better"
    assert probe_policy_metrics["threshold_passed"]["warn_pct"] == 0.0

    quantization_metrics = {
        metric["key"]: metric
        for metric in by_id["quantization-gate-manifest-event-streaming"]["metrics"]
    }
    assert quantization_metrics["events_consumed_mean"]["direction"] == "lower_is_better"
    assert quantization_metrics["events_consumed_mean"]["warn_pct"] == 0.0
    assert quantization_metrics["elapsed_ms_mean"]["direction"] == "informational"
    assert quantization_metrics["elapsed_ms_min"]["direction"] == "informational"

    release_gate_metrics = {
        metric["key"]: metric
        for metric in by_id["release-gates-m9-failure-count-single-pass"]["metrics"]
    }
    assert release_gate_metrics["endswith_checks_mean"]["direction"] == "lower_is_better"
    assert release_gate_metrics["endswith_checks_mean"]["warn_pct"] == 0.0
    assert release_gate_metrics["elapsed_ms_mean"]["direction"] == "informational"

    native_mtp_metrics = {
        metric["key"]: metric
        for metric in by_id["native-mtp-loader-safetensor-scandir"]["metrics"]
    }
    for metric_key in (
        "old_mean_ms",
        "delta_ms",
        "speedup",
        "old_peak_bytes_mean",
        "extra_old_mean_ms",
        "extra_old_peak_bytes_mean",
        "model_listing_old_mean_ms",
        "model_listing_old_peak_bytes_mean",
        "key_old_mean_ms",
        "key_delta_ms",
        "key_speedup",
    ):
        assert native_mtp_metrics[metric_key]["direction"] == "informational"
        assert "warn_pct" not in native_mtp_metrics[metric_key]
    assert native_mtp_metrics["model_listing_new_mean_ms"]["direction"] == "lower_is_better"
    assert native_mtp_metrics["model_listing_delta_ms"]["direction"] == "lower_is_better"
    assert native_mtp_metrics["model_listing_speedup"]["direction"] == "higher_is_better"
    assert native_mtp_metrics["key_new_mean_ms"]["direction"] == "lower_is_better"

    changed_scope_metrics = {
        metric["key"]: metric
        for metric in by_id["changed-scope-coverage-empty-path-short-circuit"]["metrics"]
    }
    assert changed_scope_metrics["elapsed_ms_mean"]["warn_abs"] == 0.05
    assert changed_scope_metrics["source_read_calls_mean"]["warn_pct"] == 0.0

    dataset_preview_metrics = {
        metric["key"]: metric
        for metric in by_id["dataset-registry-preview-limit-short-circuit"]["metrics"]
    }
    assert dataset_preview_metrics["elapsed_ms_mean"]["warn_abs"] == 0.5
    assert dataset_preview_metrics["peak_bytes_mean"]["warn_pct"] == 5.0


def test_scope_report_selects_probe_policy_overhead_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=[
            "services/mlx-worker-python/worker/productization/probe_policy_overhead.py"
        ],
    )

    assert "probe-policy-noop-overhead" in {probe["id"] for probe in scope["selected_probes"]}


def test_scope_report_selects_serving_diagnostics_queue_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=[
            "services/mlx-worker-python/worker/productization/serving_diagnostics.py"
        ],
    )

    assert "serving-diagnostics-debug-queue-bounds" in {
        probe["id"] for probe in scope["selected_probes"]
    }


def test_probe_policy_noop_overhead_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_PROBE_POLICY_OVERHEAD_ITERATIONS", "32")
    monkeypatch.setenv("MELIX_PROBE_POLICY_OVERHEAD_SAMPLES", "1")
    monkeypatch.setattr(sys, "argv", ["probe_policy_noop_overhead_probe.py"])

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(REPO_ROOT / "scripts/probe_policy_noop_overhead_probe.py"), run_name="__main__")

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["iteration_count"] == 32.0
    assert metrics["sample_count"] == 1.0
    assert "no_op_recorder_overhead_pct" in metrics
    assert "no_op_policy_check_overhead_pct" in metrics
    assert "no_op_reason_overhead_pct" in metrics
    assert "no_op_reason_call_ms_mean" in metrics
    assert "mode_parse_empty_call_ms_mean" in metrics
    assert "mode_parse_valid_call_ms_mean" in metrics
    assert "mode_parse_invalid_call_ms_mean" in metrics
    assert "env_parse_empty_call_ms_mean" in metrics
    assert "mode_parse_invalid_overhead_pct" in metrics


def test_serving_diagnostics_queue_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_SERVING_DIAGNOSTICS_QUEUE_CAPACITY", "4")
    monkeypatch.setenv("MELIX_SERVING_DIAGNOSTICS_QUEUE_EVENTS", "10")
    monkeypatch.setenv("MELIX_SERVING_DIAGNOSTICS_QUEUE_SAMPLES", "1")
    monkeypatch.setattr(sys, "argv", ["serving_diagnostics_queue_probe.py"])

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(REPO_ROOT / "scripts/serving_diagnostics_queue_probe.py"), run_name="__main__")

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["capacity"] == 4.0
    assert metrics["event_count"] == 10.0
    assert metrics["retained_count"] == 4.0
    assert metrics["dropped_count"] == 6.0
    assert "serialization_elapsed_ms_mean" in metrics
    assert metrics["serialization_checksum"] == 30.0


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


def test_load_probe_registry_absolutizes_relative_cache_keys(
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
    cache = pr_scoped_performance_module._PROBE_REGISTRY_CACHE
    cache.clear()
    monkeypatch.chdir(tmp_path)

    try:
        first = load_probe_registry("probe-registry.json")
        second = load_probe_registry(registry_path)
    finally:
        cache.clear()

    assert second is first


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
    original_os_stat = os.stat
    cache = pr_scoped_performance_module._PROBE_REGISTRY_CACHE
    selected_cache = pr_scoped_performance_module._SCOPE_SELECTED_PROBES_WITH_COVERAGE_CACHE
    pr_scoped_performance_module._load_probe_registry_for_scope_cached.cache_clear()
    cache.clear()
    selected_cache.clear()

    def fail_path_stat(self: Path, *args: object, **kwargs: object) -> os.stat_result:  # pragma: no cover
        raise AssertionError("scope registry loader should stat the cache-key string directly")

    def tracked_os_stat(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        *args: object,
        **kwargs: object,
    ) -> os.stat_result:
        nonlocal stat_calls
        if os.fspath(path) == os.fspath(registry_path):
            stat_calls += 1
        return original_os_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", fail_path_stat)
    monkeypatch.setattr(os, "stat", tracked_os_stat)

    try:
        first = build_scope_report(
            registry_path=registry_path,
            changed_files=["services/mlx-worker-python/worker/productization/pr_scoped_performance.py"],
        )
        second = build_scope_report(
            registry_path=registry_path,
            changed_files=["services/mlx-worker-python/worker/productization/pr_scoped_performance.py"],
        )
        selected_cache_populated = bool(selected_cache)
    finally:
        pr_scoped_performance_module._load_probe_registry_for_scope_cached.cache_clear()
        cache.clear()
        selected_cache.clear()

    assert stat_calls == 2
    assert first["selected_count"] == 1
    assert second["selected_probes"] == first["selected_probes"]
    assert selected_cache_populated
    assert build_scope_report(registry_path=registry_path, changed_files=[])["selected_probes"] == []


def test_probe_id_index_reuses_cached_mapping_without_reiterating() -> None:
    probes = (
        ProbeDefinition(
            probe_id="target",
            name="Target",
            runner="ubuntu-latest",
            watch_globs=(),
            test_command="",
            coverage_command="",
            probe_impl="command_json",
            probe_command="",
            metrics=(MetricDefinition(key="elapsed_ms_mean", unit="ms", direction="lower_is_better"),),
        ),
    )
    cache = pr_scoped_performance_module._PROBE_ID_INDEX_CACHE
    cache.clear()

    first = _probe_id_to_index(probes)
    second = _probe_id_to_index(probes)

    cache.clear()
    assert first == {"target": 0}
    assert second is first


def test_probe_id_index_reuses_cached_mapping_without_reiterating() -> None:
    probes = (
        ProbeDefinition(
            probe_id="target",
            name="Target",
            runner="ubuntu-latest",
            watch_globs=(),
            test_command="",
            coverage_command="",
            probe_impl="command_json",
            probe_command="",
            metrics=(MetricDefinition(key="elapsed_ms_mean", unit="ms", direction="lower_is_better"),),
        ),
    )
    cache = pr_scoped_performance_module._PROBE_ID_INDEX_CACHE
    cache.clear()

    first = _probe_id_to_index(probes)
    second = _probe_id_to_index(probes)

    cache.clear()
    assert first == {"target": 0}
    assert second is first


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
    assert metrics["sandbox_profile_elapsed_ms_mean"] > 0
    assert metrics["sandbox_profile_static_builds_mean"] == 1.0
    assert metrics["sandbox_profile_iteration_count"] == 1500.0


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


def test_code_eval_payload_json_probe_script_emits_metrics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe_script = runpy.run_path(str(REPO_ROOT / "scripts/code_eval_payload_json_probe.py"))

    probe_script["main"]()
    metrics = json.loads(capsys.readouterr().out)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["payload_bytes"] > 0
    assert metrics["sample_count"] == 7.0
    assert metrics["iteration_count"] == 1200.0


def test_code_eval_runner_script_probe_script_emits_metrics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe_script = runpy.run_path(str(REPO_ROOT / "scripts/code_eval_runner_script_probe.py"))

    probe_script["main"]()
    metrics = json.loads(capsys.readouterr().out)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["dedent_calls_mean"] == 1.0
    assert metrics["identity_reuse_mean"] == 1.0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["result_alloc_elapsed_ms_mean"] > 0
    assert metrics["result_alloc_peak_bytes_mean"] > 0
    assert metrics["result_alloc_iteration_count"] == 30000.0
    assert metrics["result_instance_dict_count_mean"] == 0.0
    assert metrics["iteration_count"] == 20000.0
    assert metrics["sample_count"] == 7.0


def test_code_eval_count_tests_probe_script_emits_metrics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe_script = runpy.run_path(str(REPO_ROOT / "scripts/code_eval_count_tests_probe.py"))

    probe_script["main"]()
    metrics = json.loads(capsys.readouterr().out)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["line_count"] == 8000.0
    assert metrics["iteration_count"] == 25.0
    assert metrics["sample_count"] == 7.0
    assert metrics["syntax_count"] == 5334.0
    assert metrics["no_assert_count"] == 6002.0
    assert metrics["assert_elapsed_ms_mean"] > 0
    assert metrics["assert_line_count"] == 8000.0
    assert metrics["assert_node_iterations"] == 20.0
    assert metrics["assert_count"] == 8000.0


def test_code_eval_test_count_probe_script_emits_metrics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe_script = runpy.run_path(str(REPO_ROOT / "scripts/code_eval_test_count_probe.py"))

    probe_script["main"]()
    metrics = json.loads(capsys.readouterr().out)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["line_count"] == 60000.0
    assert metrics["nonblank_line_count_mean"] == 48000.0
    assert metrics["sample_count"] == 7.0


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
    assert rerank_metrics["tokenize_calls_mean"] == 65.0
    assert rerank_metrics["score_calls_mean"] == 64.0
    assert rerank_metrics["unique_document_count"] == 64.0
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
    assert scope_matcher_metrics["command_summary_ms_mean"] > 0
    assert scope_matcher_metrics["command_summary_iterations"] == 20000.0
    assert scope_matcher_metrics["changed_file_count"] == float(len(_build_large_scope_probe_changed_files()))
    assert scope_matcher_metrics["selected_probe_count_mean"] == float(
        len(SCOPE_MATCHER_SELECTED_PROBE_IDS)
    )
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
    assert metrics["tokenize_calls_mean"] == 65.0
    assert metrics["score_calls_mean"] == 64.0
    assert metrics["unique_document_count"] == 64.0


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
    assert payload["request_lifecycle_elapsed_ms_mean"] > 0
    assert payload["request_stats_elapsed_ms_mean"] > 0
    assert payload["resident_bytes_mean"] > 0
    assert payload["sample_count"] == 3.0


def test_startup_signals_probe_script_emits_metrics(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(REPO_ROOT / "scripts/startup_signals_log_probe.py"), run_name="__main__")

    assert excinfo.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["conflict_elapsed_ms_mean"] > 0
    assert payload["conflict_log_path_exists_checks_mean"] == 0.0
    assert payload["conflict_log_reads_mean"] == 0.0
    assert payload["control_crash_elapsed_ms_mean"] > 0
    assert payload["control_crash_log_path_exists_checks_mean"] == 0.0
    assert payload["control_crash_log_reads_mean"] == 1.0
    assert payload["direct_control_crash_elapsed_ms_mean"] > 0
    assert payload["direct_control_crash_log_path_exists_checks_mean"] == 0.0
    assert payload["direct_control_crash_log_reads_mean"] == 0.0
    assert payload["worker_crash_elapsed_ms_mean"] > 0
    assert payload["worker_crash_log_path_exists_checks_mean"] == 0.0
    assert payload["worker_crash_log_reads_mean"] == 1.0
    assert payload["report_alloc_elapsed_ms_mean"] > 0
    assert payload["report_alloc_peak_bytes_mean"] > 0
    assert payload["report_has_dict_mean"] == 0.0
    assert payload["report_to_dict_checksum"] > 0
    assert payload["report_to_dict_elapsed_ms_mean"] > 0
    assert payload["report_to_dict_peak_bytes_mean"] > 0
    assert payload["tail_scan_elapsed_ms_mean"] > 0
    assert payload["tail_scan_peak_bytes_mean"] > 0
    assert payload["trailing_whitespace_bytes"] == 80000.0
    assert payload["sample_count"] == 5.0


def test_job_registry_probe_script_emits_metrics(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(REPO_ROOT / "scripts/job_registry_derived_model_probe.py"), run_name="__main__")

    assert excinfo.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["active_manifest_elapsed_ms_mean"] > 0
    assert payload["resolve_target_elapsed_ms_mean"] > 0
    assert payload["resolve_trimmed_target_elapsed_ms_mean"] > 0
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


def test_benchmark_store_probe_counts_lines_without_read_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = importlib.util.spec_from_file_location(
        "benchmark_store_probe_for_test",
        REPO_ROOT / "scripts/benchmark_store_probe.py",
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    rows_path = tmp_path / "rows.jsonl"
    rows_path.write_text("one\ntwo\nthree\n", encoding="utf-8")

    def fail_read_text(self: Path, *args: object, **kwargs: object) -> str:
        raise AssertionError(f"read_text should not count probe rows: {self}")

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    assert module._count_text_lines(rows_path) == 3.0
    with pytest.raises(AssertionError, match="read_text should not count"):
        rows_path.read_text(encoding="utf-8")


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
    assert payload["sample_count"] == 7.0
    assert payload["snapshot_count"] == 6000.0
    assert payload["selected_latest_snapshot"] == 5999.0
    assert payload["weight_scan_elapsed_ms_mean"] > 0
    assert payload["weight_file_count"] == 20_000.0


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
    assert payload["special_entry_follow_dir_checks_mean"] == 0.0


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
    assert metrics["special_entry_follow_dir_checks_mean"] == 0.0


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
    assert metrics["command_summary_ms_mean"] > 0
    assert metrics["command_summary_iterations"] == 20000.0
    assert metrics["changed_file_count"] == float(len(_build_large_scope_probe_changed_files()))
    assert metrics["selected_probe_count_mean"] == float(
        len(SCOPE_MATCHER_SELECTED_PROBE_IDS)
    )
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
    assert metrics["probe_sample_limit"] == 1.0
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

    def fake_run_command(command: str, *, cwd: Path, env=None) -> dict[str, object]:
        _ = env
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
    informational_faster = _build_metric_row(
        key="elapsed_ms_mean",
        unit="ms",
        direction="informational",
        warn_pct=5.0,
        base_metrics={"elapsed_ms_mean": 10.0},
        head_metrics={"elapsed_ms_mean": 8.0},
    )
    informational_slower = _build_metric_row(
        key="peak_bytes_mean",
        unit="bytes",
        direction="informational",
        warn_pct=5.0,
        base_metrics={"peak_bytes_mean": 100.0},
        head_metrics={"peak_bytes_mean": 120.0},
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
    assert informational_faster["delta"] == -2.0
    assert informational_faster["status"] == "neutral"
    assert informational_slower["delta"] == 20.0
    assert informational_slower["status"] == "neutral"
    assert zero_baseline["delta_pct"] is None
    with pytest.raises(ValueError, match="Unknown metric direction: 'descending'"):
        _build_metric_row(
            key="elapsed_ms_mean",
            unit="ms",
            direction="descending",
            warn_pct=5.0,
            base_metrics={"elapsed_ms_mean": 10.0},
            head_metrics={"elapsed_ms_mean": 8.0},
        )

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


def test_report_keeps_informational_metric_deltas_neutral() -> None:
    scope = {
        "changed_files": ["scripts/mlx_audio_wav_streaming_probe.py"],
        "force_all": False,
        "selected_count": 1,
        "selected_probes": [
            {
                "id": "wav",
                "name": "WAV",
                "metrics": [
                    {
                        "key": "elapsed_ms_mean",
                        "unit": "ms",
                        "direction": "informational",
                        "warn_pct": 5.0,
                    }
                ],
            }
        ],
    }
    result = {
        "probe": scope["selected_probes"][0],
        "head_verification": {
            "test": {"ok": True, "coverage_pct": None},
            "coverage": {"ok": True, "coverage_pct": 100.0},
        },
        "base_probe": {"ok": True, "metrics": {"elapsed_ms_mean": 10.0}},
        "head_probe": {"ok": True, "metrics": {"elapsed_ms_mean": 8.0}},
    }

    report = build_performance_report(scope=scope, probe_results=[result])
    row = report["rows"][0]

    assert report["summary"]["status"] == "ok"
    assert report["summary"]["regression_count"] == 0
    assert row["status"] == "ok"
    assert row["metrics"][0]["delta"] == -2.0
    assert row["metrics"][0]["status"] == "neutral"


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
    assert _summarize_command(" \n  python3 - <<'PY'  \nprint('x')") == "python3 - <<'PY' ..."
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


def test_mlx_audio_local_uri_probe_script_emits_metrics() -> None:
    probe = next(
        probe
        for probe in load_probe_registry(REGISTRY_PATH)
        if probe.probe_id == "mlx-audio-local-uri-zero-copy-preprocess"
    )

    metrics = _probe_command_json(probe=probe, repo_root=REPO_ROOT)

    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["local_uri_exists_calls_mean"] == 0.0
    assert metrics["local_uri_read_bytes_calls_mean"] == 0.0
    assert metrics["audio_size_bytes"] == 8_388_608.0
    assert metrics["sample_count"] == 5.0


def test_mlx_audio_local_uri_probe_script_main_covers_checked_in_file(
    capsys: pytest.CaptureFixture[str],
) -> None:
    script_path = REPO_ROOT / "scripts" / "mlx_audio_local_uri_probe.py"
    spec = importlib.util.spec_from_file_location("mlx_audio_local_uri_probe_test", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.AUDIO_SIZE_BYTES = 1024
    module.SAMPLE_COUNT = 1

    assert module.main() == 0
    payload = json.loads(capsys.readouterr().out.strip())

    assert payload["local_uri_exists_calls_mean"] == 0.0
    assert payload["local_uri_read_bytes_calls_mean"] == 0.0
    assert payload["audio_size_bytes"] == 1024.0
    assert payload["sample_count"] == 1.0


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


def test_melix_metrics_snapshot_discovery_probe_script_emits_metrics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe_script = runpy.run_path(str(REPO_ROOT / "scripts/melix_metrics_snapshot_discovery_probe.py"))

    assert probe_script["main"]() == 0

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 9.0
    assert metrics["file_count"] == 4000.0
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


def test_engine_generate_usage_token_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MELIX_ENGINE_GENERATE_USAGE_PROBE_REQUESTS", "3")
    monkeypatch.setenv("MELIX_ENGINE_GENERATE_FALLBACK_PROBE_REQUESTS", "2")
    monkeypatch.setenv("MELIX_ENGINE_GENERATE_USAGE_PROBE_SAMPLES", "2")
    monkeypatch.setenv("MELIX_ENGINE_GENERATE_USAGE_PROBE_PROMPT_WORDS", "32")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(REPO_ROOT / "scripts/engine_generate_usage_token_probe.py"), run_name="__main__")

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["request_count"] == 3
    assert metrics["samples"] == 2
    assert metrics["prompt_words"] == 32
    assert metrics["prompt_token_count_calls_mean"] == 0
    assert metrics["prompt_token_count_calls_per_request"] == 0
    assert metrics["request_state_append_calls_mean"] == 0
    assert metrics["request_state_append_calls_per_request"] == 0
    assert metrics["token_events_mean"] == 3
    assert metrics["fallback_request_count"] == 2
    assert metrics["fallback_elapsed_ms_mean"] > 0
    assert metrics["fallback_peak_bytes_mean"] > 0


def test_scope_report_tracks_direct_matches_separately_when_force_all(tmp_path: Path) -> None:
    registry_path = tmp_path / "probes.json"
    registry_path.write_text(
        json.dumps(
            [
                {
                    "id": "target",
                    "name": "Target",
                    "watch_globs": [
                        "src/target.py",
                        "services/mlx-worker-python/tests/test_pr_scoped_performance.py",
                    ],
                    "probe_impl": "command_json",
                    "metrics": [
                        {"key": "elapsed_ms_mean", "unit": "ms", "direction": "lower_is_better"}
                    ],
                },
                {
                    "id": "context",
                    "name": "Context",
                    "watch_globs": [
                        "src/context.py",
                        "services/mlx-worker-python/tests/test_pr_scoped_performance.py",
                    ],
                    "probe_impl": "command_json",
                    "metrics": [
                        {"key": "elapsed_ms_mean", "unit": "ms", "direction": "lower_is_better"}
                    ],
                },
            ]
        )
    )

    scope = build_scope_report(
        registry_path=registry_path,
        changed_files=[
            "src/target.py",
            "infra/perf/pr_scoped_probes.json",
            "services/mlx-worker-python/tests/test_pr_scoped_performance.py",
        ],
    )

    assert scope["force_all"] is True
    assert {probe["id"] for probe in scope["selected_probes"]} == {"target", "context"}
    assert scope["matched_probe_ids"] == ["target"]


def test_scope_report_treats_framework_force_all_paths_as_context_for_domain_probes(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "probes.json"
    registry_path.write_text(
        json.dumps(
            [
                {
                    "id": "evaluation-store-samples-csv-streaming",
                    "name": "Evaluation samples",
                    "watch_globs": [
                        "services/mlx-worker-python/worker/productization/evaluation_store.py",
                        "services/mlx-worker-python/worker/productization/pr_scoped_performance.py",
                    ],
                    "probe_impl": "command_json",
                    "metrics": [
                        {"key": "elapsed_ms_mean", "unit": "ms", "direction": "lower_is_better"}
                    ],
                },
                {
                    "id": "pr-scoped-performance-scope-matcher",
                    "name": "Scope matcher",
                    "watch_globs": [
                        "services/mlx-worker-python/worker/productization/pr_scoped_performance.py",
                    ],
                    "probe_impl": "command_json",
                    "metrics": [
                        {"key": "elapsed_ms_mean", "unit": "ms", "direction": "lower_is_better"}
                    ],
                },
            ]
        )
    )

    scope = build_scope_report(
        registry_path=registry_path,
        changed_files=[
            "services/mlx-worker-python/worker/productization/pr_scoped_performance.py"
        ],
    )

    assert scope["force_all"] is True
    assert {probe["id"] for probe in scope["selected_probes"]} == {
        "evaluation-store-samples-csv-streaming",
        "pr-scoped-performance-scope-matcher",
    }
    assert scope["matched_probe_ids"] == ["pr-scoped-performance-scope-matcher"]
    coverage_paths_by_probe = {
        str(probe["id"]): probe["coverage_paths"]
        for probe in scope["selected_probes"]
    }
    assert coverage_paths_by_probe["evaluation-store-samples-csv-streaming"] == []
    assert coverage_paths_by_probe["pr-scoped-performance-scope-matcher"] == [
        "services/mlx-worker-python/worker/productization/pr_scoped_performance.py"
    ]


def test_coverage_paths_for_probe_keeps_force_all_context_off_domain_probes() -> None:
    probe = ProbeDefinition(
        probe_id="evaluation-sample-probe-aggregation",
        name="Evaluation sample probe aggregation",
        runner="ubuntu-latest",
        watch_globs=(
            "services/mlx-worker-python/worker/engine/evaluation_core.py",
            "services/mlx-worker-python/worker/productization/pr_scoped_performance.py",
        ),
        test_command="true",
        coverage_command="true",
        probe_impl="command_json",
        probe_command='python3 -c "{}"',
        metrics=(MetricDefinition(key="elapsed_ms_mean", unit="ms", direction="lower_is_better"),),
    )

    paths = coverage_paths_for_probe(
        probe=probe,
        changed_files=[
            "services/mlx-worker-python/worker/engine/evaluation_core.py",
            "services/mlx-worker-python/worker/productization/pr_scoped_performance.py",
        ],
    )

    assert paths == ("services/mlx-worker-python/worker/engine/evaluation_core.py",)


def test_force_all_context_regressions_do_not_fail_direct_probe_gate() -> None:
    target_probe = {
        "id": "target",
        "name": "Target",
        "metrics": [{"key": "elapsed_ms_mean", "unit": "ms", "direction": "lower_is_better", "warn_pct": 5.0}],
    }
    context_probe = {
        "id": "context",
        "name": "Context",
        "metrics": [{"key": "elapsed_ms_mean", "unit": "ms", "direction": "lower_is_better", "warn_pct": 5.0}],
    }
    scope = {
        "changed_files": [
            "src/target.py",
            "infra/perf/pr_scoped_probes.json",
        ],
        "force_all": True,
        "selected_count": 2,
        "matched_probe_ids": ["target"],
        "selected_probes": [target_probe, context_probe],
    }

    report = build_performance_report(
        scope=scope,
        probe_results=[
            {
                "probe": target_probe,
                "head_verification": {
                    "test": {"ok": True, "coverage_pct": None},
                    "coverage": {"ok": True, "coverage_pct": 100.0},
                },
                "base_probe": {"ok": True, "metrics": {"elapsed_ms_mean": 10.0}},
                "head_probe": {"ok": True, "metrics": {"elapsed_ms_mean": 9.0}},
            },
            {
                "probe": context_probe,
                "head_verification": {
                    "test": {"ok": True, "coverage_pct": None},
                    "coverage": {"ok": True, "coverage_pct": 100.0},
                },
                "base_probe": {"ok": True, "metrics": {"elapsed_ms_mean": 10.0}},
                "head_probe": {"ok": True, "metrics": {"elapsed_ms_mean": 20.0}},
            },
        ],
    )

    assert report["summary"]["status"] == "ok"
    assert report["summary"]["regression_count"] == 0
    assert report["summary"]["context_regression_count"] == 1
    assert report["rows"][0]["gate"] == "direct"
    assert report["rows"][1]["gate"] == "context"
    assert report["rows"][1]["status"] == "regression"


def test_vision_family_prompt_token_count_probe_script_emits_metrics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    runpy.run_path(str(REPO_ROOT / "scripts/vision_family_prompt_token_count_probe.py"), run_name="__main__")

    metrics = json.loads(capsys.readouterr().out)

    assert metrics["token_count"] > 0
    assert metrics["split_calls_mean"] == 0.0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["config_object_footprint_bytes"] > 0


def test_scope_report_selects_deterministic_ocr_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=["services/mlx-worker-python/worker/runtime/deterministic_ocr_runtime.py"],
    )

    assert scope["selected_count"] == 1
    assert scope["selected_probes"][0]["id"] == "deterministic-ocr-token-count-scan"


def test_deterministic_ocr_token_count_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_OCR_TOKEN_COUNT_ITERATIONS", "10")
    monkeypatch.setenv("MELIX_OCR_TOKEN_COUNT_SAMPLES", "1")
    from worker.runtime.token_counting import whitespace_token_count

    def fail_cache_clear() -> None:  # pragma: no cover - exercised only on regression
        raise AssertionError("probe should call the raw helper instead of clearing the shared LRU cache")

    monkeypatch.setattr(whitespace_token_count, "cache_clear", fail_cache_clear)

    runpy.run_path(str(REPO_ROOT / "scripts/deterministic_ocr_token_count_probe.py"), run_name="__main__")

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["sample_count"] == 1.0
    assert metrics["iterations"] == 10.0
    assert metrics["token_count"] > 0
    assert metrics["helper_token_count"] > 0


def test_deterministic_vlm_completion_token_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_DETERMINISTIC_VLM_COMPLETION_PROBE_ITERATIONS", "10")
    monkeypatch.setenv("MELIX_DETERMINISTIC_VLM_COMPLETION_PROBE_SAMPLES", "1")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(REPO_ROOT / "scripts/deterministic_vlm_completion_token_probe.py"), run_name="__main__")

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["split_calls_mean"] == 0.0
    assert metrics["token_count_calls_mean"] == 1.0
    assert metrics["peak_bytes_mean"] > 0
    assert metrics["samples"] == 1
    assert metrics["iterations"] == 10
    assert metrics["completion_tokens"] > 0

    from worker.runtime.deterministic_vlm_runtime import DeterministicVLMRuntime
    from worker.runtime.multimodal_preprocessing import PreparedVisionRequest

    restored_request = PreparedVisionRequest(
        prompt_text="Describe the restored image.",
        images=[],
        videos=[],
        video_frame_policies=[],
        preprocess_latency_ms=0.0,
        preprocess_input_bytes=0,
        preprocess_peak_memory_bytes=0,
        prompt_hash_hex="p" * 64,
        multimodal_hash_hex="m" * 64,
    )
    assert "Prompt: Describe the restored image." in DeterministicVLMRuntime()._response_text(
        restored_request
    )
