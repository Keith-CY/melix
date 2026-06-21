# Retrieval lookup four-item tuple copy fast path

This Python performance slice is limited to four-item tuple handling inside
`worker.runtime.retrieval_context._copy_payload_value(...)`, which is used by
`project_retrieval_lookup_result(...)` when projecting retrieval lookup payloads
into prompt messages.

## Goal

Keep retrieval lookup projection behavior unchanged while avoiding the temporary
list allocation created for four-item tuple payload values. Tuple payloads remain
tuples, and nested mutable values are still recursively copied.

## Probe coverage

The affected path is covered by the registered PR-scoped performance probe
`retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.
The probe has focused `test_command`, `coverage_command`, and `probe_command`
entries and includes lookup payload copy metrics (`lookup_copy_*`) for the tuple
copy path.

## Verification plan

1. Run focused retrieval context tests plus registry/probe tests.
2. Run changed-scope coverage for the touched Python paths and probe script.
3. Run the registered `retrieval-context-projection-fastpath` probe locally on
   Linux against `origin/main` and this branch.
4. Use the PR-scoped performance workflow as the merge gate.

## Linux validation boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
behavior changes are included.
