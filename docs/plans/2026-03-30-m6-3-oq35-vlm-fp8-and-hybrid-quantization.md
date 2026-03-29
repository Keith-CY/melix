# M6.3 OQ3.5, VLM, FP8, And Hybrid Quantization

## Goal

Extend quantization support to mixed-profile variants, VLM-specific rules, FP8-source models, and hybrid quantization modes.

## Scope

- add specialized mixed-profile quantization
- preserve VLM-specific constraints such as selective precision retention
- support FP8-source inputs and hybrid quantization layouts

## Files

- update `services/mlx-worker-python/worker/model_ops/`
- update `services/mlx-worker-python/worker/runtime/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `tests/integration/`

## Implementation Notes

- hybrid modes must remain explicit in manifests and registry metadata
- VLM-specific rules should not leak into text-only quantization paths
- FP8-source handling should be observable and test-covered

## Verification

- `make py-test`
- `make integration-test`

## Acceptance

- mixed-profile, VLM-aware, FP8-aware, and hybrid quantization modes are supported through the quantization pipeline
- the resulting artifacts are identifiable and test-covered
