# M6.5 OQE, GPTQ, And Hessian Compensation

## Goal

Layer enhanced quantization compensation on top of the base quantization pipeline using GPTQ-style and Hessian-aware correction paths.

## Scope

- add enhanced compensation stages
- preserve compatibility with the base quantization schema
- keep enhanced modes explicit and opt-in

## Files

- update `services/mlx-worker-python/worker/model_ops/`
- update `packages/protocol/schema/worker/v1/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `tests/integration/`

## Implementation Notes

- enhanced modes should be represented as first-class profiles rather than undocumented flags
- compensation metadata should remain inspectable after artifact production
- keep enhanced modes isolated enough to benchmark independently

## Verification

- `make proto`
- `make py-test`

## Acceptance

- enhanced compensation modes can be requested and tracked explicitly
- enhanced quantization outputs are distinguishable from base outputs
