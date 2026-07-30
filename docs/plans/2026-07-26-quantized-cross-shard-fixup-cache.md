# Quantized cross-shard fixup count cache

## Scope

This Python-only performance slice is limited to
`worker.runtime.quantized_tensor_metadata.QuantizedTensorMetadata` and
`cross_shard_quantized_metadata_fixup_count()`.

Quantized model metadata is immutable after construction, but repeated native MTP
and VLM sanitization checks still recomputed the number of cross-shard
`.weight`/`.scales` pairs by scanning every tensor name. The count can be derived
once while the metadata mapping is normalized, then reused by the hot helper.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`quantized-tensor-metadata-prepass` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/quantized_tensor_metadata.py`
- `services/mlx-worker-python/worker/runtime/native_mtp/mlx_lm_loader.py`
- `services/mlx-worker-python/worker/runtime/mlx_vlm_runtime.py`
- `services/mlx-worker-python/tests/test_mlx_vlm_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/quantized_tensor_metadata_prepass_probe.py`

## Plan

1. Cache the cross-shard fixup count inside immutable quantized metadata during
   construction.
2. Preserve existing mapping normalization, tensor-name cache, and empty metadata
   singleton behavior.
3. Add a focused regression guard proving repeated fixup-count reads do not
   rescan the shard mapping.
4. Run the registered focused tests, changed-scope coverage, and quantized
   metadata probe locally on Linux before opening the PR.

## Acceptance

- Focused quantized metadata behavior tests pass locally.
- Changed-scope coverage for the touched Python files is at least 95 percent.
- The registered local probe reports a lower
  `cross_shard_fixup_elapsed_ms_mean` for repeated fixup-count reads.
- GitHub Actions and the PR-scoped performance report complete successfully
  before merge.
