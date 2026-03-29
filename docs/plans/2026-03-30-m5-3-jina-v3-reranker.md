# M5.3 Jina V3 Reranker

## Goal

Add a Jina v3 reranker path that uses family-specific scoring behavior while preserving the shared rerank API contract.

## Scope

- introduce Jina-family rerank scoring
- preserve the generic rerank response shape
- expose family identity and capability through model metadata

## Files

- update `services/mlx-worker-python/worker/runtime/`
- update `services/mlx-worker-python/worker/model_registry/catalog.py`
- update `tests/integration/test_non_text_endpoints.py`

## Implementation Notes

- scoring logic should remain isolated from the generic rerank API surface
- registry metadata should make Jina-family support explicit
- later family additions should reuse the same adapter pattern

## Verification

- `make py-test`
- `make integration-test`

## Acceptance

- Jina-family rerank models can serve through the shared rerank endpoint
- scoring behavior and top-k semantics are test-covered
