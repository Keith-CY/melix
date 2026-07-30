# Retrieval source numeric public fast path

## Scope

This Python performance slice is limited to retrieval-context projection in
`services/mlx-worker-python/worker/runtime/retrieval_context.py`.

The hot path handles complete `RetrievalContextEntry` objects and complete plain
store-record dictionaries that use source IDs shaped like `source:<digits>`.
Those IDs are already considered public by `worker.runtime.untrusted_context`,
but the projection loop still pays the helper-call/regex fallback path for every
record.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.
The registry entry already includes focused `test_command`, `coverage_command`,
and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/retrieval_context.py`
- `services/mlx-worker-python/tests/test_retrieval_context.py`
- `scripts/retrieval_context_projection_probe.py`

## Implementation plan

1. Keep projection behavior equivalent for all source IDs.
2. Add a local loop fast path for normalized source IDs matching
   `source:<digits>` and length <= 96 before falling back to
   `_is_public_source_id()`.
3. Guard the store-record path with a regression test that fails if numeric
   source IDs fall through to the public-source regex.
4. Run the focused test command, changed-scope coverage, and the registered
   probe locally on Linux before opening the PR.

## Metrics

Expected direction: lower `optimized_elapsed_ms_mean` and
`store_optimized_elapsed_ms_mean` in `scripts/retrieval_context_projection_probe.py`.
The PR-scoped performance workflow remains the merge gate.
