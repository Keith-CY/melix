# Retrieval Lookup Record Type Fastpath Performance Slice

## Context

The registered PR-scoped probe `retrieval-context-projection-fastpath` covers
`services/mlx-worker-python/worker/runtime/retrieval_context.py`, including
lookup-result projection and copy behavior. Earlier retrieval slices already
hoisted retrieval context-kind membership checks, specialized common copy
shapes, and kept tuple-backed lookup records valid when wrapper metadata is
present.

## Slice

This Python-only slice is limited to the lookup-result metadata fallback branch
inside `project_retrieval_lookup_result`. The function already computes
`records_type = type(lookup_records)` before validating the records container;
the fallback check now reuses that exact type value instead of calling
`isinstance(lookup_records, list)` again.

Behavior is unchanged:

- list-backed lookup records keep the existing projection path;
- tuple-backed lookup records remain accepted and preserve valid metadata;
- malformed or missing records still return metadata-scoped refusal receipts.

## Probe

Registered probe: `retrieval-context-projection-fastpath`

Required local Linux validation:

- Focused retrieval lookup/result tests, including tuple-record metadata
  preservation.
- Changed-scope coverage for retrieval context, the probe selector tests, and
  the projection probe script.
- `scripts/retrieval_context_projection_probe.py` through the registered probe
  command path.

## Expected Impact

The lookup-result hot path avoids one redundant `isinstance` dispatch after an
exact type lookup has already been performed. Expected gains are very small and
should be read from the registered probe's lookup-record and lookup-copy
sub-metrics, with overall projection metrics remaining neutral-to-improved.