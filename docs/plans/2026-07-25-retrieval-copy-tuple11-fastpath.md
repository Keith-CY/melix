# Retrieval lookup tuple-11 copy fast path

This Python-only performance slice is limited to tuple handling inside
`worker.runtime.retrieval_context._copy_payload_value(...)`, which is used when
`project_retrieval_lookup_result(...)` copies retrieval lookup payloads into
prompt messages.

## Scope

Recent retrieval lookup copy slices added explicit tuple fast paths through ten
items. The retrieval metadata fixture now includes eleven-field label windows
that represent richer retrieval provenance. This slice extends the same explicit
copy pattern to eleven-item tuples while leaving all other tuple lengths on their
existing path.

Behavior remains unchanged:

- tuple payloads remain tuples;
- nested mutable values are still recursively copied;
- scalar immutable values keep the existing identity-preserving copy behavior;
- non-eleven tuple lengths continue to use their existing paths.

## Registered PR-scoped probe

The affected path is covered by the registered PR-scoped performance probe
`retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.
This slice adds this plan document to the probe watch list and extends
`scripts/retrieval_context_projection_probe.py` so the lookup-copy sample
exercises the eleven-item tuple fast path.

## Verification plan

1. Extend focused regression coverage for eleven-item tuple payload copies.
2. Run the registered focused pytest command for
   `retrieval-context-projection-fastpath`.
3. Run the registered changed-scope coverage command and require at least 95%
   coverage for the touched Python scope.
4. Run the registered local probe on Linux and compare lookup-copy metrics.
5. Use GitHub Actions PR-scoped performance as the final base-vs-head merge gate
   before merging.

## Linux validation boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
behavior is changed or claimed.