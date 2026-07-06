# Deterministic rerank score loop bindings

This Python-only performance slice is limited to `DeterministicRerankRuntime.score_documents(...)` in `services/mlx-worker-python/worker/runtime/deterministic_rerank_runtime.py`.

## Scope

The deterministic rerank runtime already builds query tokens, a query-token set, and the family query context once per request, then reuses cached scores for duplicate document strings. This follow-up keeps those semantics unchanged and narrows the per-document scoring loop by binding repeated cache lookup, score append, and family scoring callables once before iterating documents.

No rerank model metadata, backend selection, query-context construction, duplicate-document cache behavior, score ordering, or response schema changes in this slice.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `deterministic-rerank-query-context-reuse` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/deterministic_rerank_runtime.py`
- `services/mlx-worker-python/worker/runtime/rerank_backends.py`
- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_rerank_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Verification plan

1. Run the registered focused rerank tests locally on Linux.
2. Run the registered changed-scope coverage command locally and require at least 95% changed-line coverage.
3. Run the registered `deterministic-rerank-query-context-reuse` probe locally against `origin/main` and this branch.
4. Use GitHub Actions PR-scoped performance as the final registered probe validation and merge gate.

## Linux validation boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime behavior changes are included.
