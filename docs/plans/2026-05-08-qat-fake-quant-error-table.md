# QAT fake-quant byte error table

## Goal

Reduce repeated per-byte floating-point reconstruction work in QAT fake-quant source statistics while preserving the manifest payload exactly.

## Touched files

- `services/mlx-worker-python/worker/model_ops/quantization_pipeline.py`
- `services/mlx-worker-python/tests/test_quantization_pipeline.py`
- `scripts/quantization_qat_source_scan_probe.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Linux-only constraint

This is a Python worker slice and is fully locally verifiable on Linux with focused pytest, changed-scope coverage, and a command-json PR-scoped performance probe.

## Performance probe

Update the existing `quantization-qat-source-scan-scandir` probe to also measure `_qat_fake_quant_source_stats(...)` over a deterministic synthetic byte workload.

Metrics:

- `source_stats_elapsed_ms_mean`: lower is better
- `source_stats_peak_bytes_mean`: informational
- `source_stats_byte_count`: structural workload size

## Success metrics

- Focused pytest passes for QAT source scanning/stats and PR-scoped probe smoke tests.
- Changed-scope coverage is at least 95% for touched executable Python files.
- Local base-vs-head PR-scoped probe shows lower `source_stats_elapsed_ms_mean` with matching structural workload metrics.
- `git diff --check` passes.

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_quantization_pipeline.py::test_qat_source_artifact_files_uses_scandir_stack_without_path_rglob \
  services/mlx-worker-python/tests/test_quantization_pipeline.py::test_qat_source_artifact_files_skips_bad_scandir_entries_and_empty_roots \
  services/mlx-worker-python/tests/test_quantization_pipeline.py::test_quantize_job_records_qat_mode_source_kind_and_release_gate_evidence \
  services/mlx-worker-python/tests/test_quantization_pipeline.py::test_qat_fake_quant_error_table_matches_reference_and_caches \
  services/mlx-worker-python/tests/test_quantization_pipeline.py::test_qat_fake_quant_source_stats_reuses_byte_error_table \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_quantization_qat_source_scan_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_quantization_qat_source_scan_probe_script_emits_metrics
```

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q ... && \
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && \
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/model_ops/quantization_pipeline.py \
  services/mlx-worker-python/tests/test_quantization_pipeline.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py \
  scripts/quantization_qat_source_scan_probe.py
```

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_QAT_SOURCE_SCAN_REPO_ROOT="$PWD" \
  uv run --project services/mlx-worker-python python3 scripts/quantization_qat_source_scan_probe.py
```
