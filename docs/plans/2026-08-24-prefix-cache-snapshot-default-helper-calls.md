# Prefix cache snapshot byte default helper calls

## Scope

This Python-only performance slice is limited to `estimate_cache_snapshot_bytes()` in `services/mlx-worker-python/worker/runtime/prefix_block_store.py`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `prefix-cache-snapshot-byte-streaming` in `infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`, `coverage_command`, and `probe_command` entries covering the prefix cache snapshot byte estimator, compatibility tests, probe registry selection, and `scripts/prefix_cache_snapshot_bytes_probe.py`.

## Optimization

`estimate_cache_snapshot_bytes()` now calls `_tensor_nbytes()` and `_tensor_pair_nbytes()` through their default `getattr` binding instead of passing the same local `get_attr` argument on every helper call. This keeps the helper semantics and fallback behavior unchanged while removing repeated third-argument setup from the per-layer snapshot byte loop.

## Verification plan

1. Run the focused prefix cache snapshot byte tests from the registered probe.
2. Run changed-scope coverage from the registered probe and remove generated `coverage.json` afterwards.
3. Run `scripts/prefix_cache_snapshot_bytes_probe.py` locally on Linux and compare with a same-environment `origin/main` baseline. `elapsed_ms_mean` and `elapsed_ms_p95` are the primary local timing gates; `checksum`, `iteration_count`, `layer_count`, and `peak_bytes_mean` should stay stable.
4. Use the PR-scoped performance workflow as the merge gate before squash merging.
