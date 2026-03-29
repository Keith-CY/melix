# M6.4 AWQ And Sensitivity Planning

## Goal

Add equalization and sensitivity-planning stages so quantization can make data-driven bit-allocation decisions before artifact generation.

## Scope

- add equalization preparation
- add sensitivity analysis and budget planning
- keep planning outputs tied to quantization manifests

## Files

- update `services/mlx-worker-python/worker/model_ops/`
- update `services/mlx-worker-python/worker/engine/maintenance_core.py`
- update `apps/macos-menubar/Sources/AppMain/`
- update `tests/integration/`

## Implementation Notes

- planning outputs should be inspectable and reproducible
- UI controls should expose high-value planning knobs without leaking implementation internals
- later enhanced quantization should reuse the same planning artifacts

## Verification

- `make py-test`
- `make integration-test`

## Acceptance

- equalization and sensitivity planning are represented as explicit quantization stages
- planning outputs are visible in artifacts, manifests, or operator state
