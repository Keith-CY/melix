# M1.8 LoRA Adapter Cache Isolation

## Goal

Prevent cache reuse across incompatible adapter sets by binding dispatch, cache, and restore identity to the active LoRA adapter configuration.

## Scope

- extend cache identity with adapter-set information
- isolate dispatch handles and restore metadata by adapter configuration
- preserve operator-visible adapter workflows

## Files

- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `services/control-plane-swift/Sources/Requests/`
- update `services/control-plane-swift/Sources/Snapshots/`
- update `services/mlx-text-worker-swift/Sources/Core/`
- update `services/mlx-worker-python/worker/model_ops/`

## Implementation Notes

- adapter identity should compose cleanly with parser mode, reasoning profile, and quant profile
- cache restore must fail safely when adapter identity is incompatible
- training and publish flows should emit enough metadata for adapter-aware cache namespacing

## Verification

- `make swift-test`
- `make py-test`
- `make integration-test`

## Acceptance

- adapter switches do not reuse incompatible cache assets
- adapter-aware cache and restore behavior is observable in integration tests
