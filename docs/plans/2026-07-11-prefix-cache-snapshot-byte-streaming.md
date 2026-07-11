# Prefix cache snapshot byte streaming

This Python-only performance slice is limited to `estimate_cache_snapshot_bytes()` in `services/mlx-worker-python/worker/runtime/prefix_block_store.py`.

## Scope

The prefix-cache hot path estimates resident KV-cache bytes after prompt-cache snapshots are cloned or restored. The previous implementation created an intermediate per-layer tensor list before summing `.nbytes` or `size * itemsize`. This follow-up slice keeps the same supported cache shapes while avoiding repeated runtime construction of the `list | tuple` type-union check inside the streamed state path.

## Registered probe

The affected path is covered by the registered PR-scoped probe `prefix-cache-snapshot-byte-streaming` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries and reports:

- `elapsed_ms_mean`, `elapsed_ms_min`, and `elapsed_ms_p95` for repeated byte-estimation calls over a synthetic multi-layer cache.
- `peak_bytes_mean` from `tracemalloc`.
- informational `iteration_count` and `layer_count`.

The older `prefix-cold-index-scandir` probe remains registered for the same module, but this new probe is the merge-gating performance signal for this byte-estimation slice.

## Plan

1. Add direct behavior coverage for state-list, key/value, scalar-state, and missing-layer cache shapes.
2. Add the registered probe script and PR-scoped registry entry for cache snapshot byte estimation.
3. Replace the per-layer temporary tensor list with direct streaming accumulation.
4. Reuse a module-level state-sequence type tuple so the streamed state path does not rebuild `list | tuple` during every layer check.
5. Run focused tests, changed-scope coverage, and the registered probe locally on Linux.
6. Use GitHub Actions PR-scoped performance as the final merge gate.

## Follow-up Slice: Deferred Nbytes Coercion

The 2026-07-11 follow-up keeps `estimate_cache_snapshot_bytes()` behavior and
supported cache shapes unchanged, but avoids coercing every discovered `.nbytes`
value through `int()` inside the per-layer loop. The fallback `size * itemsize`
path still normalizes multiplicands before computing bytes, and the function
coerces the final sum before returning so callers keep receiving a plain Python
integer. The hot path for tensor objects that already expose integer `.nbytes`
therefore removes repeated per-tensor conversion calls.

Expected effect:

- reduce `prefix-cache-snapshot-byte-streaming` `elapsed_ms_mean` and p95 for
  repeated cache byte estimation;
- preserve `peak_bytes_mean` and byte-estimate correctness;
- leave cold-tier indexing, matching, restore, and eviction behavior unchanged.

## Success criteria

- Behavior remains equivalent for existing `.state`, `.keys/.values`, `.nbytes`, and `size * itemsize` cache shapes.
- Changed-scope coverage for touched Python paths is at least 95%.
- The local registered probe shows lower elapsed time for the synthetic cache byte-estimation workload.
- GitHub Actions and the PR-scoped performance workflow complete successfully before merge.
