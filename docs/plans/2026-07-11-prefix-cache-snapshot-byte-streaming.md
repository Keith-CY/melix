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

## Follow-up Slice: Deferred Fallback Multiplication Coercion

The next 2026-07-12 follow-up keeps the same registered probe and narrows to the
`size * itemsize` fallback in `_tensor_nbytes()`. The hot fallback path now
multiplies the exposed numeric attributes directly and leaves the public
`estimate_cache_snapshot_bytes()` return coercion in place, preserving caller
behavior while avoiding per-tensor `int()` coercions inside the loop.

Success is accepted only if focused tests, changed-scope coverage, and the local
registered Linux probe pass with lower elapsed time, and if the PR-scoped CI
probe completes successfully before merge.

## Follow-up Slice: Final Int Coercion Fast Path

The 2026-07-14 follow-up keeps the same registered probe and narrows to the
final public return coercion in `estimate_cache_snapshot_bytes()`. The estimator
still returns a plain integer for callers, but the common path already accumulates
plain `int` byte counts from `.nbytes` and `size * itemsize` tensors. This slice
therefore skips the redundant `int(total)` constructor when the accumulator is
already exactly `int`, while preserving the fallback coercion for unusual numeric
tensor metadata that produces a non-`int` total.

Success is accepted only if focused tests, changed-scope coverage, and the local
registered Linux probe pass with lower elapsed time, and if the PR-scoped CI
probe completes successfully before merge.

## Follow-up Slice: State Branch Flattening

The next 2026-07-14 follow-up keeps the same registered probe and narrows to the
per-layer branch layout in `estimate_cache_snapshot_bytes()`. The estimator now
binds `getattr` once and handles the `.state is None` keys/values path as the
first branch, then handles state sequences and scalar state objects without the
extra `continue` jumps. This preserves the existing `.state`, `.keys/.values`,
`.nbytes`, and `size * itemsize` behavior while trimming interpreter dispatch in
the repeated snapshot byte-estimation loop.

Success is accepted only if focused tests, changed-scope coverage, and the local
registered Linux probe pass with lower elapsed time, and if the PR-scoped CI
probe completes successfully before merge.

## Follow-up Slice: Pair-State Unpack Fast Path

The 2026-07-18 follow-up keeps the same registered probe and narrows to the
common two-tensor `.state` cache sequence. Instead of checking `len(state) == 2`
and then indexing the pair, `estimate_cache_snapshot_bytes()` now attempts a
pair unpack, sums the two tensors directly on success, and falls back to the
existing generic loop for empty, singleton, or longer list/tuple state sequences.
This preserves the supported `.state`, `.keys/.values`, `.nbytes`, and
`size * itemsize` behaviors while avoiding repeated length and subscript work in
the pair-state hot path.

Success is accepted only if focused tests, changed-scope coverage, and the local
registered Linux probe pass with lower elapsed time, and if the PR-scoped CI
probe completes successfully before merge.

## Follow-up Slice: Exact Sequence Type Check

The 2026-07-22 follow-up keeps the same registered probe and narrows to the
common exact `list` / `tuple` `.state` cache sequence shapes produced by prompt
cache layers. `estimate_cache_snapshot_bytes()` now binds `type` once and uses
an exact-type membership check before the existing pair-unpack path, avoiding
the more general `isinstance(..., (list, tuple))` dispatch in the repeated
snapshot byte-estimation loop while preserving supported exact list/tuple,
scalar `.state`, and `.keys` / `.values` behavior.

Success is accepted only if focused tests, changed-scope coverage, and the local
registered Linux probe pass with lower elapsed time, and if the PR-scoped CI
probe completes successfully before merge.

## Follow-up Slice: Direct Exact Sequence Type Branch

The 2026-07-22 follow-up keeps the same registered probe and narrows to exact
list/tuple state detection in `estimate_cache_snapshot_bytes()`. The prior
exact-type slice used tuple membership against a bound sequence-type tuple; this
slice branches directly on `type(state) is list or type(state) is tuple`, avoiding
the membership lookup while preserving the same exact list/tuple, scalar
`.state`, and `.keys` / `.values` behavior.

Success is accepted only if focused tests, changed-scope coverage, and the local
registered Linux probe pass with lower elapsed time, and if the PR-scoped CI
probe completes successfully before merge.

## Follow-up Slice: Tensor Pair Byte Helper

The 2026-07-24 follow-up keeps the same registered probe and narrows to the
common two-tensor state/key-value shapes observed by
`estimate_cache_snapshot_bytes()`. The tensor byte helper now binds Python's
`getattr` once as a function default, and paired `.state` plus `.keys` / `.values`
paths use a two-tensor helper so the hot loop avoids an extra helper call while
preserving the existing `.nbytes`, `size * itemsize`, missing-size, and
missing-itemsize behavior.

Success is accepted only if focused tests, changed-scope coverage, and the local
registered Linux probe pass with lower elapsed time, and if the PR-scoped CI
probe completes successfully before merge.

## Follow-up Slice: Hot Loop Getattr Binding Reuse

The next 2026-07-24 follow-up keeps the same registered probe and narrows to the
already-bound `getattr` local in `estimate_cache_snapshot_bytes()`. The estimator
now passes that binding into the scalar and pair tensor byte helpers from every
state, key, and value path instead of relying on each helper's default argument
lookup, preserving byte accounting behavior while shaving dispatch overhead in
the repeated snapshot byte-estimation loop.

Success is accepted only if focused tests, changed-scope coverage, and the local
registered Linux probe pass with lower elapsed time, and if the PR-scoped CI
probe completes successfully before merge.

## Follow-up Slice: State Sequence Branch First

The 2026-07-25 follow-up keeps the same registered probe and narrows to the
branch order inside `estimate_cache_snapshot_bytes()`. The synthetic prompt-cache
workload and MLX prompt-cache layers are dominated by exact list/tuple `.state`
sequences, so this slice checks that sequence branch before the less-common
`.state is None` keys/values fallback. Behavior remains unchanged for exact
list/tuple state sequences, scalar state objects, and `.keys` / `.values` layers.

Success is accepted only if focused tests, changed-scope coverage, and the local
registered Linux probe pass with lower elapsed time, and if the PR-scoped CI
probe completes successfully before merge.

## Follow-up Slice: State Sequence Alias Elision

The 2026-07-25 follow-up keeps the same registered probe and narrows to the
exact list/tuple `.state` branch in `estimate_cache_snapshot_bytes()`. The branch
already proves the local `state` object is a sequence, so this slice removes the
extra `state_sequence` alias and unpacks / iterates `state` directly. Behavior is
unchanged for pair sequences, non-pair sequences, scalar `.state` values, and
`.keys` / `.values` fallback layers; the change only trims one local assignment
inside the repeated byte-estimation hot loop.

Success is accepted only if focused tests, changed-scope coverage, and the local
registered Linux probe pass with lower elapsed time, and if the PR-scoped CI
probe completes successfully before merge.

## Follow-up Slice: Final Type Check Binding Reuse

The 2026-07-27 follow-up keeps the same registered probe and narrows to the
final return coercion in `estimate_cache_snapshot_bytes()`. The hot loop already
binds `type` to `type_of` for per-layer state dispatch, so the final public
integer-preserving check now reuses that same local binding instead of resolving
the global `type` builtin again. Behavior is unchanged: exact `int` totals are
returned directly, and uncommon non-`int` numeric totals are still coerced with
`int(total)` before returning.

Success is accepted only if focused tests, changed-scope coverage, and the local
registered Linux probe pass with lower elapsed time, and if the PR-scoped CI
probe completes successfully before merge.

## Follow-up Slice: Pair First Tensor Direct Nbytes

The next 2026-07-27 follow-up keeps the same registered probe and narrows to the
first tensor in `_tensor_pair_nbytes()`. The synthetic prompt-cache workload and
common MLX pair shapes expose `.nbytes` on the first tensor, so this slice reads
that attribute directly and only falls back to the existing `size * itemsize`
path on `AttributeError`. The second tensor keeps the previous defaulted
`getattr()` flow because fallback-shaped tensors are common there.

Behavior remains unchanged for pair state and key/value layers: first tensors
with `.nbytes` use the fast path, first tensors without `.nbytes` still use the
fallback byte shape when present, and unusual non-`int` totals are still coerced
by `estimate_cache_snapshot_bytes()` before return.

Success is accepted only if focused tests, changed-scope coverage, and the local
registered Linux probe pass with lower elapsed time, and if the PR-scoped CI
probe completes successfully before merge.

## Follow-up Slice: Scalar Tensor Direct Nbytes

The next 2026-07-27 follow-up keeps the same registered probe and narrows to the
scalar tensor path in `_tensor_nbytes()`. The prompt-cache byte estimator now
reads `.nbytes` directly for scalar state, key-only, value-only, and generic
sequence tensors, then falls back to the existing `size * itemsize` path when
`.nbytes` is missing or explicitly `None`. This mirrors the pair first-tensor
fast path while preserving fallback behavior for tensor-like objects that expose
only shape metadata.

Success is accepted only if focused tests, changed-scope coverage, and the local
registered Linux probe pass with lower elapsed time, and if the PR-scoped CI
probe completes successfully before merge.

## Follow-up Slice: Pair Second Tensor Direct Fallback Bytes

The 2026-07-27 follow-up keeps the same registered probe and narrows to the
second tensor fallback inside `_tensor_pair_nbytes()`. The registered workload's
pair state and key/value layers commonly expose `.nbytes` on the first tensor and
`size * itemsize` metadata on the second tensor, so this slice reads the second
tensor's fallback `size` and `itemsize` attributes directly and only takes the
zero-byte path on `AttributeError` or missing `itemsize`.

Behavior remains unchanged for pair state and key/value layers: second tensors
with `.nbytes` still return that value, fallback-shaped tensors still use
`size * itemsize`, missing-size or missing-itemsize tensors still contribute zero,
and uncommon non-`int` totals are still coerced by
`estimate_cache_snapshot_bytes()` before return.

Success is accepted only if focused tests, changed-scope coverage, and the local
registered Linux probe pass with lower elapsed time, and if the PR-scoped CI
probe completes successfully before merge.

## Follow-up Slice: Missing State Branch First

The 2026-07-30 follow-up keeps the same registered probe and narrows to the
per-layer branch order in `estimate_cache_snapshot_bytes()`. Cache layers that
omit `.state` and expose `.keys` / `.values` do not need an exact `type(state)`
check, so this slice handles `state is None` first and only resolves `type(state)`
for real scalar or sequence state objects. Behavior is unchanged for exact
list/tuple state sequences, scalar state tensors, and `.keys` / `.values` layers;
the change only avoids one type lookup on missing-state layers in the repeated
snapshot byte-estimation loop.

Success is accepted only if focused tests, changed-scope coverage, and the local
registered Linux probe pass with lower elapsed time, and if the PR-scoped CI
probe completes successfully before merge.
