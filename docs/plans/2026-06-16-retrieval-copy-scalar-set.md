# Retrieval lookup copy scalar-type membership slice

## Scope

This Python-only performance slice is limited to the JSON scalar fast path in
`worker.runtime.retrieval_context._copy_payload_value()`.

The helper recursively copies retrieval lookup payloads before exposing prompt
projection output. The common payload path contains many JSON scalar leaves
(`str`, `int`, `float`, and `bool`), and the previous implementation tested each
scalar type through a chain of identity comparisons on every recursive leaf.

## Registered probe coverage

The affected path is covered by the registered PR-scoped probe
`retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.
That probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries, and reports the lookup-copy metrics
`lookup_copy_optimized_elapsed_ms_mean`, `lookup_copy_delta_ms`, and
`lookup_copy_speedup`.

## Implementation plan

1. Preserve behavior for copied payload isolation, including nested dict/list/
   tuple containers and fallback `deepcopy` for non-JSON objects.
2. Replace the repeated scalar identity comparison chain with a module-level
   exact-type membership set for JSON scalar types.
3. Run the focused retrieval-context tests and registered probe coverage command
   locally on Linux.
4. Run the registered retrieval-context projection probe locally on Linux and use
   GitHub Actions PR-scoped performance as the final merge gate.

## Verification

Local Linux verification must include:

- focused retrieval-context pytest coverage from the registered probe scope;
- changed-scope coverage for `worker.runtime.retrieval_context` at or above 95%;
- the registered `retrieval-context-projection-fastpath` probe command.

The slice does not touch Swift runtime code; Swift/macOS runtime effects are not
claimed locally.
