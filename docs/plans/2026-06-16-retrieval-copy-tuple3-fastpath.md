# Retrieval lookup tuple-3 copy fast path

This Python-only performance slice is limited to tuple handling inside
`worker.runtime.retrieval_context._copy_payload_value(...)`, which is used when
`project_retrieval_lookup_result(...)` copies retrieval lookup payloads into
prompt messages.

## Scope

The previous slice fast-pathed zero-, one-, and two-item tuple payload values.
This slice extends that same behavior to the common three-item metadata tuple
without changing payload isolation semantics:

- tuple payloads remain tuples;
- nested mutable values are still recursively copied;
- longer tuples continue to use the existing generic copy path.

## Registered PR-scoped probe

The affected path is covered by the registered PR-scoped performance probe
`retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.
The registered entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries. This slice adds this plan document to the probe watch
list and adjusts `scripts/retrieval_context_projection_probe.py` so the lookup
copy sample includes a three-item tuple payload.

## Verification plan

1. Add focused regression coverage for three-item tuple payload copies.
2. Run the registered focused pytest command for
   `retrieval-context-projection-fastpath`.
3. Run the registered changed-scope coverage command and require at least 95%
   coverage for the touched Python scope.
4. Run the registered local probe on Linux and compare lookup-copy metrics.
5. Use GitHub Actions PR-scoped performance as the final base-vs-head merge
   gate before merging.

## Linux validation boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
behavior is changed or claimed.
