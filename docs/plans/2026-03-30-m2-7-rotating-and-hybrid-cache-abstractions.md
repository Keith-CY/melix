# M2.7 Rotating And Hybrid Cache Abstractions

## Goal

Add the cache abstractions needed for long-context and mixed-mode execution where a single cache strategy is insufficient.

## Scope

- define rotating-cache and hybrid-cache abstractions
- make them compatible with the shared cache metadata model
- avoid exposing unfinished experimental behavior as default runtime policy

## Files

- update `packages/protocol/schema/worker/v1/`
- update `services/mlx-text-worker-swift/Sources/Core/`
- update `services/control-plane-swift/Sources/Snapshots/`
- update `docs/architecture-spec.md`

## Implementation Notes

- abstractions should remain internal until benchmark evidence is stable
- shared metadata should still describe restore boundaries and byte ownership clearly
- keep experimental modes behind explicit runtime policy flags

## Verification

- `make proto`
- `make swift-test`

## Acceptance

- rotating and hybrid cache modes are representable in runtime policy and metrics
- they do not destabilize the default cache path
