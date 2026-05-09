# Rerank Duplicate Document Score Cache

## Goal

Reduce redundant deterministic rerank scoring work when a single request contains repeated document texts. The runtime should score each unique document once per request, then reuse the score while preserving output order and duplicate positions.

## Touched Files

- `services/mlx-worker-python/worker/runtime/deterministic_rerank_runtime.py`
- `services/mlx-worker-python/tests/test_rerank_runtime.py`
- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Linux-only Constraint

This is a Python worker optimization and can be locally verified on Linux with focused pytest, changed-scope coverage, and the existing PR-scoped performance harness.

## Probe Definition

Update the existing `deterministic-rerank-query-context-reuse` probe to use a duplicate-heavy synthetic document set and report structural duplicate-score reuse metrics:

- `tokenize_calls_mean`: should drop from one query plus every document to one query plus each unique document.
- `score_calls_mean`: should equal the unique document count per iteration on the optimized path.
- `unique_document_count`: confirms the synthetic workload shape.
- `elapsed_ms_mean`: lower is better, but structural metrics are the primary gate.

## Success Metrics

- Focused rerank tests pass.
- Changed executable coverage for touched Python files is at least 95%.
- Local probe reports `score_calls_mean == unique_document_count` and `tokenize_calls_mean == unique_document_count + 1`.
- `git diff --check` passes.
