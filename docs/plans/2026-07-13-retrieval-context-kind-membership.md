# Retrieval Context Kind Membership Performance Slice

## Context

The registered PR-scoped probe `retrieval-context-projection-fastpath` covers
`services/mlx-worker-python/worker/runtime/retrieval_context.py`, including the
optimized `RetrievalContextEntry` and complete dict store-record projection hot
paths. Recent slices already inline receipt construction, direct admission, and
record type guards. The remaining hot loops still repeated the same two-value
context-kind membership literals.

## Slice

This Python-only slice hoists the retrieval context-kind set to a module-level
constant and binds it locally before the projection loops. It also binds `type`
locally in `project_retrieval_contexts`, matching the existing store-record fast
path pattern. Behavior stays unchanged: only `retrieved_document` and
`retrieved_image` are accepted, malformed entries still fall back to existing
refusal paths, and receipt contents remain unchanged.

## Probe

Registered probe: `retrieval-context-projection-fastpath`

Required local Linux validation:

- Focused retrieval context projection tests.
- Changed-scope coverage for retrieval context, probe selection tests, and the
  projection probe script.
- `scripts/retrieval_context_projection_probe.py` through the registered
  `command_json` probe path.

## Expected Impact

The projection loops avoid repeated two-value literal membership checks and a
global `type` lookup on the exact-entry path. Expected gains are small but should
be visible in the registered probe's `optimized_elapsed_ms_mean`, with store and
lookup sub-metrics remaining directionally neutral or improved.

## Follow-up Slice: Direct Context Kind Comparison

The 2026-07-17 follow-up keeps the same registered probe and narrows to the two
valid retrieval context-kind checks in the exact `RetrievalContextEntry` and
exact dict store-record hot paths. The previous slice hoisted the two valid
literals into a local frozenset; this slice replaces that membership lookup with
explicit string comparisons for the same two accepted values. Malformed kinds
still fall through to the existing refusal/admission paths, and receipt contents
remain unchanged.

Success is accepted only if the focused retrieval context tests, changed-scope
coverage, and the registered Linux probe pass locally with lower
`optimized_elapsed_ms_mean`, and if the PR-scoped CI probe completes successfully
before merge.

## Follow-up Slice: Public Source Prefix Slice Comparison

The 2026-07-19 follow-up keeps the same registered probe and narrows to the
`source:` public-id fast path used by exact `RetrievalContextEntry` objects and
exact dict store records. The previous implementation used
`normalized_source_id.startswith(public_source_prefix)` before slicing the numeric
suffix; this slice uses a fixed-length prefix slice comparison instead, reusing
the already-bound prefix length and preserving the same fallback to
`_is_public_source_id()` for non-numeric or non-prefixed public source ids.

Success is accepted only if the focused retrieval context tests,
changed-scope coverage, and the registered Linux probe pass locally with lower
`optimized_elapsed_ms_mean`, and if the PR-scoped CI probe completes successfully
before merge.
