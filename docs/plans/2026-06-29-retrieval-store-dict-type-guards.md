# Retrieval store record exact type guards

This Python-only performance slice is limited to the complete plain-dict fast path in `worker.runtime.retrieval_context.project_retrieval_store_records`.

## Scope

Retrieval store projection is repeatedly exercised by the registered retrieval-context projection probe. Complete store records are plain dictionaries with exact `str`, `dict`, and `bool` fields. The existing fast path still validates those exact plain-dict records with repeated `isinstance(...)` calls before normalizing metadata and building receipts.

This slice keeps fallback behavior for malformed records, mapping-like records, and non-exact field values unchanged: records that do not satisfy the exact plain-dict fast path still flow through the existing admission path. The only hot-path change is replacing the complete plain-dict fast-path validation with exact `type(...) is ...` guards so common records avoid generic `isinstance` dispatch.

## Registered probe

The affected path is covered by the registered PR-scoped probe `retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/retrieval_context.py`
- `services/mlx-worker-python/tests/test_retrieval_context.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/retrieval_context_projection_probe.py`

## Local verification plan

Run on Linux before opening the PR:

1. Focused retrieval-context tests from the registered probe, including a regression test that monkeypatches module-level `isinstance` to prove complete plain dict store records stay on the exact type-guard fast path.
2. Changed-scope coverage from the registered probe.
3. The registered retrieval-context projection probe locally with repeated samples.

GitHub Actions PR-scoped performance remains the final registered probe validation and merge gate.

## Success criteria

- Store record projection semantics remain unchanged for complete records, duplicate fields, public/non-public source IDs, and fallback admissions.
- Changed-scope coverage for touched Python files remains at least 95%.
- The registered local and CI probes show non-regression or improvement for the store-record metrics (`store_optimized_elapsed_ms_mean`, `store_delta_ms`, and `store_speedup`).
