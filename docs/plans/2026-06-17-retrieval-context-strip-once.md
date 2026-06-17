# Retrieval context direct projection strip-once fast path

This Python-only performance slice is limited to the direct `RetrievalContextEntry`
projection path in `worker.runtime.retrieval_context.project_retrieval_contexts(...)`.

## Scope

The direct complete-entry path already bypasses the generic admission helper for
validated `RetrievalContextEntry` objects. This slice keeps that behavior and
normalizes hot receipt fields exactly once before both validation and receipt
construction:

- `source_id`
- `segment_id`
- `source_field`
- `reason`
- `corrective_action`

Malformed or incomplete entries still fall through to the existing generic
admission/refusal path. Duplicate field handling and payload projection semantics
are unchanged.

## Registered PR-scoped probe

The affected path is covered by the registered PR-scoped performance probe
`retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.
The registered entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries. This slice adds this plan document to the probe watch
list so documentation-only adjustments to this optimization plan continue to
select the same probe.

## Verification plan

1. Run the registered focused pytest command for
   `retrieval-context-projection-fastpath`.
2. Run the registered changed-scope coverage command and require at least 95%
   coverage for the touched Python scope.
3. Run the registered local probe on Linux and compare base vs head metrics.
4. Use GitHub Actions PR-scoped performance as the final base-vs-head merge gate
   before merging.

## Linux validation boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
behavior is changed or claimed.
