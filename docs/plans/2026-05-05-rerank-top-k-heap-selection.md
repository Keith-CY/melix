# Rerank Top-K Selection Optimization

## Goal

Reduce redundant ranking work in the Python rerank API response path when callers request a small `top_k` subset of a much larger document set.

## Linux-only constraint

This slice is Python-only and can be verified on Linux with focused pytest, changed-scope coverage, and a local PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/engine/rerank_core.py`
- `services/mlx-worker-python/tests/test_rerank_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`
- `scripts/rerank_top_k_probe.py`

## Performance probe

Register `rerank-core-top-k-heap-selection` in the PR-scoped performance registry.

The probe builds a deterministic synthetic score vector for a large rerank result set and compares the production top-k selector path through `RerankCore._rank_scores(...)` on `origin/main` and the PR branch. It records:

- `elapsed_ms_mean` (lower is better)
- `peak_bytes_mean` (lower is better)
- `document_count`
- `top_k`
- `result_count`
- `checksum`

## Success metrics

- Preserve descending score ordering and original-index tie breaking.
- Preserve full-sort behavior when `top_k` is omitted, zero, or greater than the result size.
- Improve `elapsed_ms_mean` for `top_k << document_count` against `origin/main`.
- Maintain at least 95% changed-scope coverage for touched executable Python files.

## 2026-05-05 follow-up slice

This follow-up keeps the same registered probe and narrows the already-bounded
heap path by materializing sortable `(-score, index, score)` triples for the heap
instead of passing a per-item key lambda to `heapq.nsmallest(...)`. The returned
API remains `[(index, score), ...]`, so response ordering and tie-break semantics
stay unchanged while the bounded selection path avoids repeated Python key
callback dispatch. The registered coverage and probe commands use `python3` for
repository command-policy compliance.
