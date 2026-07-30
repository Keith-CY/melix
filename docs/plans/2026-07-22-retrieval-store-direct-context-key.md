# Retrieval store direct dict key slice

This Python-only performance slice is limited to `worker.runtime.retrieval_context.project_retrieval_store_records`.

## Scope

The valid retrieval-store record hot path receives plain `dict` records with all required fields present. Before this slice, the loop bound `record.get`, fetched `context_kind` through the method call, then used direct indexing for the remaining fields. This slice moves the direct `context_kind` lookup into the existing exact-dict fast path and only falls back to `record.get` when a required key is missing or a non-dict mapping is being processed.

Behavior remains unchanged for invalid record objects, missing keys, invalid `context_kind`, mapping subclasses, duplicate fields, non-public source IDs, and projection fallback paths.

## Registered probe

The affected path is covered by the registered PR-scoped probe `retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/retrieval_context.py`
- `services/mlx-worker-python/tests/test_retrieval_context.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/retrieval_context_projection_probe.py`

## Local verification plan

Run on Linux before opening the PR:

1. Focused retrieval-context tests from the registered probe.
2. Changed-scope coverage from the registered probe.
3. The registered probe command locally with repeated samples.

GitHub Actions PR-scoped performance remains the final registered probe validation and merge gate.

## Success criteria

Accept only if the registered local probe shows a lower `store_optimized_elapsed_ms_mean` / positive `store_speedup`, focused tests and changed-scope coverage pass, and the PR-scoped CI probe succeeds before merge.
