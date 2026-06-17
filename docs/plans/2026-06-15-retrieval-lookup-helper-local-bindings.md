# Retrieval Lookup Helper Local Bindings

## Summary

This Python-only performance slice keeps retrieval lookup projection behavior
unchanged and narrows one hot path in
`worker.runtime.retrieval_context.project_retrieval_lookup_result()`.

The lookup projection path calls the store projection helper, then defensively
copies the projected prompt payload and receipt lists. The slice binds those
module-level helpers to local variables once per lookup projection call, avoiding
repeated global helper lookup overhead while preserving the same copy semantics
and output structure.

## Probe Coverage

Registered probe: `retrieval-context-projection-fastpath` in
`infra/perf/pr_scoped_probes.json`.

The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` fields and watches:

- `services/mlx-worker-python/worker/runtime/retrieval_context.py`
- `services/mlx-worker-python/tests/test_retrieval_context.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/retrieval_context_projection_probe.py`

The probe reports direct projection, store-record projection, and lookup-copy
metrics, including `lookup_copy_optimized_elapsed_ms_mean` and
`lookup_copy_speedup` for this slice.

## Implementation

1. Keep the invalid lookup-result refusal path unchanged.
2. Bind `project_retrieval_store_records`, `_copy_payload`, and `_copy_receipts`
   to locals before executing the valid lookup projection path.
3. Leave payload/receipt defensive copying and lookup message construction
   semantics unchanged.

## Validation Plan

Run the registered focused test command, changed-scope coverage command, and
registered probe locally on Linux. Use the GitHub Actions PR-scoped performance
workflow as the merge gate after opening the PR.
