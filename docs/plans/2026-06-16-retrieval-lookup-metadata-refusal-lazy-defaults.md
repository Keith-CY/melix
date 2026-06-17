# Retrieval Lookup Metadata Refusal Lazy Defaults

## Scope

This Python-only performance slice is limited to
`worker.runtime.retrieval_context._lookup_result_metadata_refusal`, the guard
that validates optional retrieval lookup wrapper metadata before projection.

## Registered PR-scoped probe

The affected path is covered by the registered PR-scoped performance probe
`retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.
The entry already includes focused `test_command`, `coverage_command`, and
`probe_command` entries for the retrieval-context projection path, including the
lookup-wrapper metadata refusal scenario.

## Optimization

Keep behavior unchanged, but defer fallback/default string normalization in
`_lookup_result_metadata_refusal` until a specific metadata field is invalid.
The common valid-metadata path now only performs validity checks and avoids
allocating fallback source/segment strings that are unused when the helper
returns `None`.

## Verification plan

1. Add a focused regression/performance guard proving the valid metadata helper
   path does not call the default-normalization helper.
2. Run the registered focused pytest command for `retrieval-context-projection-fastpath`.
3. Run the registered changed-scope coverage command and require at least 95%
   coverage for the touched scope.
4. Run the registered local probe on Linux and compare the lookup-records
   metadata-refusal metrics against the pre-change probe sample.
5. Use GitHub Actions PR-scoped performance as the final base-vs-head merge
   gate.

## Environment boundary

This slice is Python-only and locally verifiable on Linux. No Swift runtime
claim is made for this change.
