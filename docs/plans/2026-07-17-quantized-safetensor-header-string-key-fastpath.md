# Quantized safetensor header string-key fast path

## Scope

This Python-only performance slice is limited to `worker.runtime.quantized_tensor_metadata._safetensors_header_tensor_names()`.

Safetensors headers are JSON objects, so decoded tensor-name keys are already strings on the hot path. The helper still called `str(key)` for every header key before filtering empty names, which adds repeated string-conversion calls while scanning large multi-shard quantized model headers.

## Registered probe

The affected path is covered by the registered PR-scoped probe `quantized-tensor-metadata-prepass` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/quantized_tensor_metadata.py`
- `services/mlx-worker-python/tests/test_mlx_vlm_runtime.py`
- `scripts/quantized_tensor_metadata_prepass_probe.py`

## Plan

1. Preserve header parsing, `__metadata__` skipping, empty-name filtering, and non-string fallback behavior.
2. Fast-path decoded string keys by appending the key directly when it is non-empty.
3. Keep the `str(key)` fallback for non-standard mappings used by direct helper callers.
4. Run the registered focused tests, changed-scope coverage, and quantized metadata probe locally on Linux before opening the PR.

## Acceptance

- Focused quantized metadata behavior tests pass locally.
- Changed-scope coverage for the touched Python files is at least 95 percent.
- The registered local probe reports a lower `header_elapsed_ms_mean` for the safetensor header prepass workload.
- GitHub Actions and the PR-scoped performance report complete successfully before merge.
