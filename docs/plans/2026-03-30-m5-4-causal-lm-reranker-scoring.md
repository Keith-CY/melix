# M5.4 Causal-LM Reranker Scoring

## Goal

Add causal-LM reranker support, including yes-no logit scoring, without forking the shared rerank API surface.

## Scope

- introduce causal-LM rerank scoring
- add yes-no logit scoring semantics
- preserve the shared rerank request and response contract

## Files

- update `services/mlx-worker-python/worker/runtime/`
- update `services/mlx-worker-python/worker/model_registry/catalog.py`
- update `tests/integration/`

## Implementation Notes

- scoring adapters should separate family-specific prompt and scoring logic from the endpoint contract
- registry metadata should declare when yes-no scoring is in effect
- keep rerank metrics comparable across architecture families

## Verification

- `make py-test`
- `make integration-test`

## Acceptance

- causal-LM rerank models can score and rank documents through the shared rerank path
- yes-no scoring behavior is explicitly test-covered
