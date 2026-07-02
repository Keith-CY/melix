# Retrieval lookup tuple-5 copy fast path

This Python-only performance slice is limited to tuple handling inside
`worker.runtime.retrieval_context._copy_payload_value(...)`, used when
`project_retrieval_lookup_result(...)` copies retrieval lookup payloads into
prompt messages.

## Scope

Previous retrieval lookup copy slices added explicit fast paths for zero- through
four-item tuple payloads. This slice extends the same pattern to five-item
metadata tuples observed in retrieval lookup payloads while leaving the longer
tuple fallback unchanged.

Behavior remains unchanged:

- tuple payloads remain tuples;
- nested mutable values are still recursively copied;
- scalar immutable values keep the existing identity-preserving copy behavior;
- longer tuples continue to use the existing generic copy path.

An attempted generic `tuple(generator)` fallback was measured locally and was
rejected because it was slower than the existing `tuple(list)` fallback for the
same five-item tuple sample. The accepted slice is the explicit five-item tuple
fast path.

## Registered PR-scoped probe

The affected path is covered by the registered PR-scoped performance probe
`retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.
The registered entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries. This slice adds this plan document to the probe watch
list and extends `scripts/retrieval_context_projection_probe.py` so the lookup
copy sample exercises the five-item tuple fast path.

## Verification plan

1. Extend focused regression coverage for five-item tuple payload copies.
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
