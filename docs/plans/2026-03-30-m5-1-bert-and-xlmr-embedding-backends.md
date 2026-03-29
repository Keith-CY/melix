# M5.1 BERT And XLM-R Embedding Backends

## Goal

Add native embedding backends for BERT-family and XLM-R-family models so embedding support is not limited to the current basic path.

## Scope

- define backend entrypoints for BERT and XLM-R embeddings
- preserve the shared embedding response contract
- keep backend selection visible in registry metadata

## Files

- update `services/mlx-worker-python/worker/runtime/`
- update `services/mlx-worker-python/worker/model_registry/catalog.py`
- update `tests/integration/test_non_text_endpoints.py`

## Implementation Notes

- backend boundaries should remain clear so future embedding families do not collapse into one file
- output semantics must remain consistent across embedding families
- registry metadata should identify family capabilities explicitly

## Verification

- `make py-test`
- `make integration-test`

## Acceptance

- BERT and XLM-R embedding backends can serve through the shared embeddings endpoint
- family-specific behavior is integration-tested
