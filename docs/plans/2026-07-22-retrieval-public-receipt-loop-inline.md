# Retrieval public receipt loop inline

## Scope

This Python performance slice is limited to retrieval-context projection in
`services/mlx-worker-python/worker/runtime/retrieval_context.py`.

The hot path handles complete `RetrievalContextEntry` objects and complete plain
store-record dictionaries whose source IDs are already public. Prior slices moved
these records away from generic admission and regex-heavy receipt construction;
this slice removes the remaining private helper call from the per-record public
receipt path by constructing the small receipt dictionary directly in the loop.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.
The registry entry already includes focused `test_command`, `coverage_command`,
and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/retrieval_context.py`
- `services/mlx-worker-python/tests/test_retrieval_context.py`
- `scripts/retrieval_context_projection_probe.py`

## Implementation plan

1. Keep public and untrusted receipt payloads byte-for-byte equivalent.
2. Inline public receipt dictionary construction inside the complete-entry and
   complete-store-record projection loops.
3. Extend regression guards so complete public entries and store records fail if
   they re-enter either public receipt helper.
4. Run the focused test command, changed-scope coverage, and registered probe
   locally on Linux before opening the PR.

## Metrics

Expected direction: lower `optimized_elapsed_ms_mean` and
`store_optimized_elapsed_ms_mean` in `scripts/retrieval_context_projection_probe.py`.
The PR-scoped performance workflow remains the merge gate.
