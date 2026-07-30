# Quantized scales tensor-name set performance slice

## Scope

This Python performance slice is limited to `worker.runtime.quantized_tensor_metadata` membership checks used by native multimodal quantization decisions.

## Registered probe

The affected path is covered by the registered PR-scoped probe `quantized-tensor-metadata-prepass` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/quantized_tensor_metadata.py`
- `services/mlx-worker-python/worker/runtime/native_mtp/mlx_lm_loader.py`
- `services/mlx-worker-python/worker/runtime/mlx_vlm_runtime.py`
- `services/mlx-worker-python/tests/test_mlx_vlm_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/quantized_tensor_metadata_prepass_probe.py`

## Optimization plan

`QuantizedTensorMetadata` already materializes an immutable `_tensor_names` snapshot during construction. This slice routes hot tensor-presence checks through that cached frozenset instead of the mapping proxy. `quantized_scales_present()` also checks the cached set directly in this module-local hot path, avoiding an extra method dispatch before falling back to materialized weight lookup.

Behavior remains unchanged: shard lookup still uses `tensor_to_shard`, public `tensor_names` remains stable, and empty weight mappings still skip unnecessary fallback membership checks.

## Verification

Local Linux validation must run:

1. The registered focused tests for `quantized-tensor-metadata-prepass`.
2. The registered changed-scope coverage command.
3. The registered local probe command.

GitHub Actions PR-scoped performance remains the final registered probe merge gate.

## Expected metrics

The primary expected direction is lower `metadata_decision_elapsed_ms_mean` in the registered probe. `high_precision_decision_elapsed_ms_mean` and `tensor_names_access_elapsed_ms_mean` should remain within the probe warning threshold because this slice changes only membership dispatch and does not alter parsing or tensor-name snapshot materialization.
