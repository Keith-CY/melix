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
