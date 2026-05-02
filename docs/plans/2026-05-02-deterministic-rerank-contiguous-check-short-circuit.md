# Deterministic Rerank Contiguous-Check Short Circuit

## Scope

This slice targets the Python deterministic rerank scoring path only:

- `services/mlx-worker-python/worker/runtime/rerank_backends.py`
- `services/mlx-worker-python/worker/runtime/deterministic_rerank_runtime.py`
- `services/mlx-worker-python/tests/test_rerank_runtime.py`

The goal is to keep scoring semantics unchanged while avoiding the ordered contiguous-query scan for documents that cannot contain all query terms.

## Registered Probe

The affected path is covered by the PR-scoped registered probe `deterministic-rerank-query-context-reuse` in `infra/perf/pr_scoped_probes.json`.

The registered probe includes:

- `test_command`: focused rerank runtime tests plus PR-scoped performance selection/dispatch tests.
- `coverage_command`: changed-scope coverage for the rerank runtime, rerank backend, PR-scoped performance harness, and related tests.
- `probe_command`: local/CI command for `_probe_deterministic_rerank_query_context_reuse`.

## Implementation Plan

1. Add a focused regression test proving the contiguous-query helper is not invoked when a document misses required query terms.
2. Gate exact-order and prefix bonuses behind the already computed overlap count in Jina-v3 and causal-LM scoring.
3. Run the focused tests, changed-scope coverage, and registered probe locally on Linux.
4. Compare the registered probe against `origin/main` before accepting the slice.

## Success Criteria

- Focused rerank behavior remains unchanged.
- Changed-scope coverage remains at or above 95%.
- Registered probe `elapsed_ms_mean` improves or shows an explainable neutral boundary without semantic regression.
