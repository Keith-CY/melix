# M2.6 Hot And Cold Cache Tiers

## Goal

Establish an explicit RAM hot tier and SSD cold tier with write-back behavior and observable restore paths.

## Scope

- formalize hot-tier and cold-tier storage behavior
- add write-back and restore coordination
- expose tier-specific hit rates and byte accounting

## Files

- update `services/mlx-text-worker-swift/Sources/Core/HotCacheStore.swift`
- update `services/mlx-text-worker-swift/Sources/Core/DiskCacheStore.swift`
- update `services/control-plane-swift/Sources/Snapshots/CacheMetadataStore.swift`
- update `tests/integration/test_recovery_flows.py`

## Implementation Notes

- tiering should remain safe for restart and eviction paths
- tier-specific metrics must distinguish hot reuse from cold restore
- write-back should not block interactive request completion unnecessarily

## Verification

- `make swift-test`
- `make integration-test`

## Acceptance

- hot-tier and cold-tier behavior are explicit in cache state and metrics
- write-back and restore flows are measurable and restart-safe
