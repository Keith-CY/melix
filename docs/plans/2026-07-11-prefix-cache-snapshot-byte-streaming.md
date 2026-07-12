# Prefix Cache Snapshot Byte Streaming Local nbytes Slice

## Context

The registered PR-scoped probe `prefix-cache-snapshot-byte-streaming` covers
`services/mlx-worker-python/worker/runtime/prefix_block_store.py` and the
snapshot byte estimator used by prefix-cache accounting.

The current estimator repeatedly performs the same `nbytes` / `size * itemsize`
lookup pattern for state, key, and value tensors. This slice keeps behavior
unchanged while reducing duplicated attribute lookup code in the hot loop.

## Scope

- Add a tiny local helper for tensor byte extraction in
  `estimate_cache_snapshot_bytes`.
- Preserve support for both older `.state` caches and newer `.keys` / `.values`
  cache shapes.
- Add focused regression coverage for state sequence fallback tensors so the
  helper preserves `size * itemsize` behavior.
- Run the registered test, coverage, and probe commands locally on Linux.

## Measurement

Registered probe: `prefix-cache-snapshot-byte-streaming`

Required commands:

- Focused tests from the registry entry.
- Changed-scope coverage from the registry entry.
- Registered probe command from the registry entry.

Success is accepted only if behavior tests pass, changed-scope coverage remains
at or above the repository threshold, and the probe reports a clear non-regressive
or improved elapsed-time result versus the baseline measurement captured before
this slice.

## Linux Boundary

This is a Python worker path and can be validated locally on Linux. CI remains
the source of truth for the PR-scoped performance workflow report after push.

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

## Follow-up Slice: State Pair Unroll

The 2026-07-12 follow-up keeps the same registered probe and targets the common
two-tensor `.state` cache shape. `estimate_cache_snapshot_bytes()` now unrolls
length-2 state sequences before falling back to the generic loop, preserving the
existing behavior for empty, one-item, and longer state sequences while reducing
iterator overhead in the synthetic and MLX prompt-cache hot path.

Success is accepted only after the local focused test command, changed-scope
coverage command, and registered probe all pass, and after the PR-scoped CI
probe validates the same registry entry.
