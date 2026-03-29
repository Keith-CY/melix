# M6.7 KV-Cache Quantization Acceleration

## Goal

Add feature-flagged KV-cache quantization acceleration so memory pressure can be reduced on long-running decode paths with measurable trade-offs.

## Scope

- add runtime policy for KV-cache quantization acceleration
- preserve correctness-first behavior for the default path
- expose metrics for memory reduction and throughput impact

## Files

- update `services/mlx-text-worker-swift/Sources/Core/Inference/`
- update `services/mlx-text-worker-swift/Sources/Core/Runtime/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `apps/macos-menubar/Sources/AppMain/`

## Implementation Notes

- acceleration should remain opt-in and benchmarked
- runtime metrics must distinguish active-path acceleration from storage-boundary quantization
- keep the policy surface compatible with per-model acceleration settings

## Verification

- `make swift-test`
- `make integration-test`
- touched-scope benchmark command for the acceleration slice

## Acceptance

- KV-cache quantization acceleration can be enabled through explicit policy
- memory and throughput effects are measurable and benchmarked
