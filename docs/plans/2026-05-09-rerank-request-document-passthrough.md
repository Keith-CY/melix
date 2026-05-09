# Rerank Request Document Passthrough Optimization

## Goal

Avoid materializing a duplicate Python `list` for `RerankRequest.documents` before dispatching to the deterministic rerank runtime.

## Touched Files

- `services/mlx-worker-python/worker/engine/rerank_core.py`
- `services/mlx-worker-python/worker/runtime/deterministic_rerank_runtime.py`
- `services/mlx-worker-python/tests/test_rerank_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/rerank_top_k_probe.py`

## Linux-only Constraint

This is a Python worker slice and can be verified on Linux with focused pytest, changed-scope coverage, and the existing PR-scoped rerank performance probe.

## Performance Probe

Use the existing registered probe `rerank-core-top-k-heap-selection`, extending `scripts/rerank_top_k_probe.py` with request-document passthrough metrics:

- `request_document_identity_hits`
- `request_document_iterations`
- `request_elapsed_ms`

## Success Metrics

- Rerank request behavior and top-k ordering remain unchanged.
- Focused tests pass.
- Changed executable line coverage is at least 95%.
- The local probe reports `request_document_identity_hits == request_iteration_count`, proving the runtime sees the original request document iterable instead of a copied list.
