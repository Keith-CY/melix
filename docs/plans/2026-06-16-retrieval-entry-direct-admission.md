# Retrieval Context Entry Direct Admission

## Scope

This Python-only performance slice is limited to
`project_retrieval_contexts(...)` in
`services/mlx-worker-python/worker/runtime/retrieval_context.py`.

The hot path receives already-normalized `RetrievalContextEntry` instances from
retrieval callers. Previous slices optimized persisted store-record projection,
lookup wrapper metadata, and payload copying; this slice applies the same direct
projection pattern to complete in-memory entries so the common path avoids
re-entering `_admit_entry(...)` and re-materializing a single-item
`PromptContextAdmission` wrapper.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.
The registry entry already includes focused `test_command`, `coverage_command`,
and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/retrieval_context.py`
- `services/mlx-worker-python/tests/test_retrieval_context.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/retrieval_context_projection_probe.py`

No registry change is required for this slice.

## Plan

1. Add a regression test proving complete `RetrievalContextEntry` values project
   without calling `_admit_entry(...)`, while preserving receipt normalization.
2. Add a direct-entry fast path that validates the same complete-field contract
   used by `_admit_context(...)` for the common path.
3. Keep malformed entries, subclassed entries, and multi-receipt monkeypatched
   admission cases on the existing fallback path.
4. Run the registered focused tests, changed-scope coverage, and registered probe
   locally on Linux.
5. Use GitHub Actions PR-scoped performance as the merge gate.

## Success criteria

- Focused retrieval-context tests pass.
- Changed-scope coverage remains at or above the repository threshold.
- The registered local probe shows a lower direct projection
  `optimized_elapsed_ms_mean` versus the current implementation, without
  regressing store or lookup-copy metrics.
- GitHub Actions and the PR-scoped performance workflow are green before merge.
