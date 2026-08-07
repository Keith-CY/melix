# Prefix snapshot state length fast path

## Scope

This Python-only performance slice is limited to `estimate_cache_snapshot_bytes()` in `services/mlx-worker-python/worker/runtime/prefix_block_store.py`.

Prompt-cache layers may expose `state` as a two-item key/value sequence or as a non-pair sequence of tensors. The previous implementation used tuple-unpack plus `ValueError` fallback to distinguish pair vs non-pair sequences, which preserves behavior but makes non-pair layers pay exception overhead on every byte-estimation pass.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `prefix-cache-snapshot-byte-streaming` in `infra/perf/pr_scoped_probes.json`. The entry has focused `test_command`, `coverage_command`, and `probe_command` entries and reports `elapsed_ms_mean`, `elapsed_ms_min`, `elapsed_ms_p95`, `iteration_count`, `layer_count`, `peak_bytes_mean`, and `sample_count`.

This slice updates `scripts/prefix_cache_snapshot_bytes_probe.py` so the synthetic cache includes non-pair `state` sequences. That keeps the registered probe aligned with the optimized branch in `estimate_cache_snapshot_bytes()`.

## Optimization plan

1. Keep exact byte-accounting semantics for scalar state, key/value layers, two-item state pairs, and arbitrary-length state sequences.
2. Replace exception-driven two-item detection with an explicit `len(state) == 2` check for list/tuple states.
3. Preserve the existing focused behavior tests and registered probe script coverage.
4. Run focused tests, changed-scope coverage, and the registered probe locally on Linux before opening the PR.
5. Use GitHub Actions PR-scoped performance as the merge-gate source of truth.

## Verification

- Focused prefix snapshot byte tests pass.
- Changed-scope coverage for touched Python/test/probe/plan files remains at or above 95%.
- Local registered probe should reduce `elapsed_ms_mean` for mixed two-item and non-pair state sequences while preserving the checksum.
