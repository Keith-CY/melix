# Retrieval Store Record Get Reuse

## Scope

This Python performance slice is limited to `project_retrieval_store_records(...)`
in `services/mlx-worker-python/worker/runtime/retrieval_context.py`.

The optimized path is the fallback admission path for mapping-like retrieval
store records. The implementation reuses fields already read from the record
instead of issuing a second round of `record.get(...)` lookups before constructing
the defensive `RetrievalContextEntry` fallback.

## Probe Coverage

The affected path is covered by the registered PR-scoped probe
`retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries that exercise retrieval context projection, retrieval
store record projection, lookup-result wrapping, changed-scope coverage, and the
synthetic projection performance probe.

This slice adds this plan file to that probe's `watch_globs` so future PR-scoped
selection continues to include the governing plan when the retrieval store record
fallback is changed.

## Verification Plan

1. Run the focused retrieval context test selection from the registered probe.
2. Run changed-scope coverage through the registered `coverage_command`.
3. Compare `origin/main` and this branch with
   `scripts/pr_scoped_performance_run.py --probe-id retrieval-context-projection-fastpath`.
4. Use the GitHub Actions PR-scoped performance report as the merge gate.

## Success Criteria

- Focused retrieval tests pass.
- Changed-scope coverage for modified Python/test lines is at least 95%.
- The registered Linux probe reports no in-scope regression for retrieval store
  metrics, especially `store_optimized_elapsed_ms_mean` and related lookup/store
  projection metrics.
- The probe's `store_mapping_get_calls_mean` metric drops for mapping-like store
  records because the fallback reuses the first field-read pass instead of
  repeating those `get(...)` calls during defensive admission construction.
