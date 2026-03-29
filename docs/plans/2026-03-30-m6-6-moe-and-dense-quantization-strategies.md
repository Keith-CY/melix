# M6.6 MoE And Dense Quantization Strategies

## Goal

Split quantization strategy between MoE and dense architectures so model-specific constraints do not leak into one generic pipeline.

## Scope

- distinguish MoE and dense quantization planning
- add family-aware strategy selection
- preserve one operator-facing quantize workflow

## Files

- update `services/mlx-worker-python/worker/model_ops/`
- update `services/mlx-worker-python/worker/model_registry/catalog.py`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `tests/integration/`

## Implementation Notes

- strategy selection should come from detected architecture and explicit overrides
- operator workflows should remain simple while manifests capture the deeper strategy choice
- benchmark evidence should remain comparable across architecture classes

## Verification

- `make py-test`
- `make integration-test`

## Acceptance

- MoE and dense architectures can select different quantization strategies
- strategy selection is represented in manifests and tests
