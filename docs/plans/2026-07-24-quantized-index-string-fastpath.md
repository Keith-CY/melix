# Quantized index string fast path

## Scope

This Python-only performance slice is limited to
`worker.runtime.quantized_tensor_metadata.quantized_tensor_metadata_from_index_payload()`.

Safetensors index `weight_map` payloads come from JSON and therefore use decoded
string tensor names and shard names on the hot path. The helper still called
`str(...)` for every tensor and shard name before constructing immutable metadata,
which adds avoidable normalization work for large quantized model indexes.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`quantized-tensor-metadata-prepass` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/quantized_tensor_metadata.py`
- `services/mlx-worker-python/tests/test_mlx_vlm_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/quantized_tensor_metadata_prepass_probe.py`

## Plan

1. Preserve empty tensor-name filtering and non-string fallback normalization.
2. Fast-path string tensor names and shard names by reusing them directly.
3. Add a focused regression test for the string fast path while keeping the
   existing non-string normalization-once coverage.
4. Run the registered focused tests, changed-scope coverage, and quantized
   metadata probe locally on Linux before opening the PR.

## Acceptance

- Focused quantized metadata behavior tests pass locally.
- Changed-scope coverage for the touched Python files is at least 95 percent.
- The registered local probe reports a lower `index_elapsed_ms_mean` for the
  index metadata prepass workload.
- GitHub Actions and the PR-scoped performance report complete successfully
  before merge.
