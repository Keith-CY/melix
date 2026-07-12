# Retrieval Store Strip Local Binding Performance Slice

## Context

The registered PR-scoped probe `retrieval-context-projection-fastpath` covers
`services/mlx-worker-python/worker/runtime/retrieval_context.py`, including the
complete plain-dict store-record fast path in `project_retrieval_store_records`.
The previous retrieval context slices already avoid admission re-entry and
inline receipt construction for complete records. This slice keeps the same
behavior and narrows the store-record hot loop overhead.

## Slice

Bind repeated exact-type guards and `str.strip` lookups to local variables in
`project_retrieval_store_records` before iterating store records. The fast path
still accepts only exact built-in `str`, `dict`, and `bool` values for complete
plain dict records, still normalizes source metadata once, and still falls back
to admission/refusal handling for malformed or mapping-like records.

## Probe

Registered probe: `retrieval-context-projection-fastpath`

Required local Linux validation:

- Focused retrieval context tests for store-record fast paths.
- Changed-scope coverage for the retrieval context probe selection and behavior.
- `scripts/retrieval_context_projection_probe.py` through the registered
  `command_json` probe path.

## Expected Impact

This should reduce optimized store-record projection mean latency for the
complete-dict path without changing retrieval context receipt contents or
refusal behavior.
