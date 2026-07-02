# Retrieval lookup single-key dict copy fast path

This Python performance slice is limited to one-entry `dict` handling inside
`worker.runtime.retrieval_context._copy_payload_value(...)`, which is used by
`project_retrieval_lookup_result(...)` when projecting retrieval lookup payloads
into prompt messages.

## Goal

Keep retrieval lookup projection behavior unchanged while avoiding the generic
dictionary-comprehension loop for common one-key nested retrieval metadata
dictionaries. Dict payloads remain dicts, and nested mutable values are still
recursively copied.

## Probe coverage

The affected path is covered by the registered PR-scoped performance probe
`retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.
The probe has focused `test_command`, `coverage_command`, and `probe_command`
entries and includes lookup payload copy metrics (`lookup_copy_*`). This slice
updates the probe fixture to include a one-key nested `single_key_detail` dict so
the registered probe exercises the new branch.

## Verification plan

1. Run focused retrieval context tests plus registry/probe tests.
2. Run changed-scope coverage for the touched Python paths and probe script.
3. Run the registered `retrieval-context-projection-fastpath` probe locally on
   Linux and compare the lookup-copy metric to the pre-change local baseline.
4. Use the PR-scoped performance workflow as the merge gate.

## Linux validation boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
behavior changes are included.
