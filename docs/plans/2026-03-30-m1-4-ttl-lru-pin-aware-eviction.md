# M1.4 TTL, LRU, And Pin-Aware Eviction

## Goal

Replace TTL-only unloading behavior with a unified eviction policy that respects time-to-live, recency, and pinning.

## Scope

- implement LRU tracking for loaded models
- preserve TTL behavior as one eviction signal rather than the only signal
- ensure pinned models remain protected from ordinary eviction

## Files

- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- update `services/control-plane-swift/Sources/WorkerClient/`
- update `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`

## Implementation Notes

- eviction reasons should be explicit and operator-visible
- LRU state should refresh on load, inference admission, and explicit operator actions
- pin-aware behavior must remain deterministic even under concurrent load decisions

## Verification

- `make swift-test`
- `make integration-test`

## Acceptance

- eviction behavior uses both TTL and recency signals
- pinned models are not evicted by ordinary LRU pressure
- eviction reasons are visible in control-plane state and metrics
