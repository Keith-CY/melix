# Model-ops manifest final-encode reuse

## Scope

This Python-only optimization slice targets the model-ops bundle manifest path in:

- `services/mlx-worker-python/worker/model_ops/conversion_pipeline.py`
- `services/mlx-worker-python/worker/model_ops/quantization_pipeline.py`

Both pipelines currently iterate in memory until `manifest_bytes` converges, then call
`_write_manifest(...)`, which re-encodes the same final manifest payload one more time just to write
identical bytes to disk. The manifest encoding is deterministic, so the final converged bytes can be
reused for the disk write instead of paying for one extra JSON encode per pipeline run.

## Linux-only constraint

The touched path is entirely inside the Python worker workspace, so Linux local verification is the
primary correctness gate. Hosted `pr-scoped-performance` remains the merge gate for the registered
probe.

## Registered probe

The affected path is already covered by the registered PR-scoped probe
`model-ops-bundle-artifact-byte-accounting` in `infra/perf/pr_scoped_probes.json`.

Relevant metrics:

- `elapsed_ms_mean`
- `bundle_scandir_calls_mean`

## Success metrics

1. Conversion and quantization manifests still converge to the same `manifest_bytes` value and the
   same persisted JSON payload.
2. The final write path reuses the converged encoded bytes instead of re-encoding the same manifest
   payload inside `_write_manifest(...)`.
3. Focused changed-scope coverage for the touched executable files remains at least `95%`.
4. The local registered probe shows a non-regressive `elapsed_ms_mean` and preserves
   `bundle_scandir_calls_mean`.

## Task list

1. Add or update focused tests that prove the final encoded manifest bytes are reused for the last
   write in both pipelines.
2. Implement a small helper path in both pipelines so the final convergence loop returns reusable
   encoded bytes while preserving manifest payload shape and file contents.
3. Run the registered focused pytest selection, changed-scope coverage, `git diff --check`, and the
   registered probe locally on Linux before commit.

## Validation commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_quantization_pipeline.py::test_quantize_job_writes_bundle_directory_and_versioned_manifest services/mlx-worker-python/tests/test_quantization_pipeline.py::test_quantize_job_writes_manifest_once_after_in_memory_byte_convergence services/mlx-worker-python/tests/test_quantization_pipeline.py::test_quantize_pipeline_counts_artifact_bytes_without_rescanning_bundle_directory services/mlx-worker-python/tests/test_maintenance_service.py::test_convert_model_writes_manifest_once_after_in_memory_byte_convergence services/mlx-worker-python/tests/test_maintenance_service.py::test_convert_pipeline_counts_artifact_bytes_without_rescanning_bundle_directory services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_ops_bundle_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_model_ops_bundle_probe
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_quantization_pipeline.py::test_quantize_job_writes_bundle_directory_and_versioned_manifest services/mlx-worker-python/tests/test_quantization_pipeline.py::test_quantize_job_writes_manifest_once_after_in_memory_byte_convergence services/mlx-worker-python/tests/test_quantization_pipeline.py::test_quantize_pipeline_counts_artifact_bytes_without_rescanning_bundle_directory services/mlx-worker-python/tests/test_maintenance_service.py::test_convert_model_writes_manifest_once_after_in_memory_byte_convergence services/mlx-worker-python/tests/test_maintenance_service.py::test_convert_pipeline_counts_artifact_bytes_without_rescanning_bundle_directory services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_ops_bundle_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_model_ops_bundle_probe
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/conversion_pipeline.py services/mlx-worker-python/worker/model_ops/quantization_pipeline.py services/mlx-worker-python/worker/productization/pr_scoped_performance.py services/mlx-worker-python/tests/test_quantization_pipeline.py services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id model-ops-bundle-artifact-byte-accounting --base-repo /tmp/melix-cron-20260503131814-base --head-repo "$PWD" --output /tmp/model_ops_bundle_probe.json
git diff --check
```
