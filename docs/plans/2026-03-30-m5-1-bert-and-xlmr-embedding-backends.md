# M5.1 BERT And XLM-R Embedding Backends

## Goal

Add native embedding backends for BERT-family and XLM-R-family models so embedding support is not limited to the current basic path.

## Scope

- define backend entrypoints for BERT and XLM-R embeddings
- preserve the shared embedding response contract
- keep backend selection visible in registry metadata

## Files

- add `services/mlx-worker-python/worker/runtime/embedding_backends.py`
- update `services/mlx-worker-python/worker/runtime/deterministic_embedding_runtime.py`
- update `services/mlx-worker-python/worker/model_registry/catalog.py`
- update `services/mlx-worker-python/tests/test_embedding_runtime.py`
- update `tests/integration/test_non_text_endpoints.py`

## Implementation Notes

- backend entrypoints are isolated in `embedding_backends.py` so later families can extend dispatch without reworking the shared runtime shell
- BERT and XLM-R keep the same embedding response shape while using distinct canonicalization and projection paths
- worker catalog metadata exposes `embedding_backend_id`, `embedding_family_id`, `embedding_pooling_mode`, `embedding_normalization`, and `embedding_dimensions`
- integration coverage uses the shared `/v1/embeddings` endpoint with an environment override for the XLM-R backend path

## Verification

- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_embedding_runtime.py -q`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest tests/integration/test_non_text_endpoints.py -q`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest tests/integration/test_runtime_core_acceptance.py -k runtime_core_keeps_text_embedding_and_rerank_models_warm_concurrently -q`
- changed-line coverage for touched Python files
- `git diff --check`

## Acceptance

- BERT and XLM-R embedding backends can serve through the shared embeddings endpoint
- family-specific behavior is integration-tested

## Metrics Report

- Python verification: `services/mlx-worker-python/tests/test_embedding_runtime.py` -> `6 passed`
- Python verification: `tests/integration/test_non_text_endpoints.py` -> `6 passed`
- Runtime-core coexistence verification: `tests/integration/test_runtime_core_acceptance.py -k runtime_core_keeps_text_embedding_and_rerank_models_warm_concurrently` -> `1 passed`
- Python changed-line coverage: `96.88% (93/96)`
