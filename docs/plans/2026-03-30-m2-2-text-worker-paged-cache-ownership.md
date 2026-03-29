# M2.2 Text-Worker Paged Cache Ownership

## Goal

Rebuild text-worker cache ownership around page and block primitives so cache reuse is no longer limited to prefix-level bookkeeping.

## Scope

- replace prefix-only hot-cache ownership with paged structures
- preserve existing restore behavior while the new ownership model lands
- keep cache accounting measurable during the transition

## Files

- update `services/mlx-text-worker-swift/Sources/Core/HotCacheStore.swift`
- update `services/mlx-text-worker-swift/Sources/Core/DiskCacheStore.swift`
- update `services/mlx-text-worker-swift/Sources/Core/WorkerServices.swift`
- update `services/mlx-text-worker-swift/Tests/CoreTests/`

## Implementation Notes

- paged ownership should support later copy-on-write and per-block reuse work
- existing cache stats must stay meaningful while the store layout changes
- the migration should avoid breaking restart-safe snapshot restore

## Verification

- `make swift-test`
- `make integration-test`

## Acceptance

- text-worker cache state is represented by page and block structures instead of prefix-only records
- cache stats and restore behavior remain test-covered during the migration
