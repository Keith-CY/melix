# Convert/Quantize Artifact Byte Accounting Optimization Plan

## Goal

Remove redundant post-write bundle directory rescans in the Python convert and quantize pipelines while preserving manifest payloads, artifact byte counts, and output file contents.

## Constraints

- Host verification is Linux-only.
- The slice must stay within Python worker code that can be verified locally.
- Changed executable scope must reach at least 95% automated coverage before commit.
- The change must remain compatible with Melix PR-scoped performance CI.

## Touched Files

- `services/mlx-worker-python/worker/model_ops/conversion_pipeline.py`
- `services/mlx-worker-python/worker/model_ops/quantization_pipeline.py`
- `services/mlx-worker-python/tests/test_maintenance_service.py`
- `services/mlx-worker-python/tests/test_quantization_pipeline.py`
- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Waste Being Removed

Both pipelines write a fixed bundle payload (`config.json`, `tokenizer.json`, `weights.safetensors`) and then rescan the bundle directory to recompute `artifact_bytes`. That second pass adds avoidable filesystem iteration and stat work after the code already knows the exact bytes written.

## Implementation Approach

1. Add small write helpers that return the exact encoded byte count for JSON and binary bundle files.
2. Accumulate `artifact_bytes` during file writes instead of rescanning the bundle directory.
3. Preserve the existing in-memory manifest-size convergence loop and final manifest serialization.
4. Add regression tests that fail if either pipeline falls back to rescanning the bundle directory for artifact byte accounting.
5. Register a PR-scoped performance probe for the convert/quantize pipeline path so CI can compare base vs head on repeated bundle runs.

## Performance Probe

- **Probe ID:** `model-ops-bundle-artifact-byte-accounting`
- **Path:** `worker/productization/pr_scoped_performance.py`
- **Measurement:** repeated convert + quantize bundle runs with `os.scandir` tracking for `*.artifact` directories
- **Success metrics:**
  - `bundle_scandir_calls_mean` decreases from the base branch by eliminating redundant post-write rescans
  - `elapsed_ms_mean` does not regress materially
  - bundle outputs and manifest payloads remain valid

## Verification Commands

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_quantization_pipeline.py::test_quantize_job_writes_bundle_directory_and_versioned_manifest \
  services/mlx-worker-python/tests/test_quantization_pipeline.py::test_quantize_job_writes_manifest_once_after_in_memory_byte_convergence \
  services/mlx-worker-python/tests/test_quantization_pipeline.py::test_quantize_pipeline_counts_artifact_bytes_without_rescanning_bundle_directory \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_convert_model_writes_manifest_once_after_in_memory_byte_convergence \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_convert_pipeline_counts_artifact_bytes_without_rescanning_bundle_directory \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_ops_bundle_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_model_ops_bundle_probe

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_quantization_pipeline.py::test_quantize_job_writes_bundle_directory_and_versioned_manifest \
  services/mlx-worker-python/tests/test_quantization_pipeline.py::test_quantize_job_writes_manifest_once_after_in_memory_byte_convergence \
  services/mlx-worker-python/tests/test_quantization_pipeline.py::test_quantize_pipeline_counts_artifact_bytes_without_rescanning_bundle_directory \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_convert_model_writes_manifest_once_after_in_memory_byte_convergence \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_convert_pipeline_counts_artifact_bytes_without_rescanning_bundle_directory \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_ops_bundle_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_model_ops_bundle_probe
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/model_ops/conversion_pipeline.py \
  services/mlx-worker-python/worker/model_ops/quantization_pipeline.py \
  services/mlx-worker-python/worker/productization/pr_scoped_performance.py \
  services/mlx-worker-python/tests/test_quantization_pipeline.py \
  services/mlx-worker-python/tests/test_maintenance_service.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 -c "import json; from pathlib import Path; from worker.productization.pr_scoped_performance import _probe_model_ops_bundle_artifact_bytes as probe; print(json.dumps(probe(Path.cwd()), sort_keys=True))"

git diff --check
```