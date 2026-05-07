# Rerank order-match first-token skip

## Scope

This Linux-safe optimization narrows the deterministic rerank order-aware hot path in `services/mlx-worker-python/worker/runtime/rerank_backends.py`. The current contiguous-query and ordered-pair helpers still perform unnecessary per-position work on document tokens whose first token cannot possibly match the query phrase or an adjacent query pair.

## Files

- `services/mlx-worker-python/worker/runtime/rerank_backends.py`
- `services/mlx-worker-python/tests/test_rerank_runtime.py`

## Goal

Reduce redundant sequence comparison and adjacent-pair tuple construction for long rerank documents with sparse query-token starts, while preserving existing deterministic score semantics.

## Linux constraint

This slice is Python-only and can be verified on Linux with focused pytest, changed-scope coverage, and a local base-vs-head PR-scoped performance probe.

## Registered probe

Use the existing registered PR-scoped performance probe `deterministic-rerank-query-context-reuse`, which already watches the touched rerank runtime/backend files and runs a synthetic multi-document rerank workload.

## Success metrics

- Focused rerank tests pass.
- Changed-scope coverage is at least 95% for changed executable lines.
- The registered `deterministic-rerank-query-context-reuse` probe is equal or faster than `origin/main` while preserving structural metrics (`query_context_builds_mean`, `tokenize_calls_mean`).
