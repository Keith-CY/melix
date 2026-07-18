# Quantized cross-shard direct lookup fast path

## Scope

This Python-only performance slice is limited to `worker.runtime.quantized_tensor_metadata.cross_shard_quantized_metadata_fixup_count()`.

The cross-shard metadata fixup counter is used after quantized tensor metadata is preloaded from model index/header data. The previous implementation built separate temporary `weights` and `scales` dictionaries before counting mismatched shard pairs. That preserved behavior but added avoidable allocation and a second lookup structure on large quantized model maps.

## Registered probe

The affected path is covered by the registered PR-scoped probe `quantized-tensor-metadata-prepass` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/quantized_tensor_metadata.py`
- `services/mlx-worker-python/tests/test_mlx_vlm_runtime.py`
- `scripts/quantized_tensor_metadata_prepass_probe.py`

## Plan

1. Preserve counting semantics: only prefixes with both `.weight` and `.scales` entries count, and only when their shard names differ.
2. Iterate weight tensor names directly and probe the paired `.scales` key in the immutable metadata mapping.
3. Avoid constructing temporary per-suffix dictionaries in the hot count path.
4. Run the registered focused tests, changed-scope coverage, and quantized metadata probe locally on Linux before opening the PR.

## Acceptance

- Focused quantized metadata behavior tests pass locally.
- Changed-scope coverage for the touched Python files is at least 95 percent.
- The registered local probe reports a lower `cross_shard_fixup_elapsed_ms_mean` and lower `cross_shard_fixup_peak_bytes_mean` for the quantized metadata workload.
- GitHub Actions and the PR-scoped performance report complete successfully before merge.