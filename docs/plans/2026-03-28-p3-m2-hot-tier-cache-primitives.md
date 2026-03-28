# P3-M2 Hot-Tier Cache Primitives

## Summary

`P3-M2` implements the first real worker-owned hot-tier cache metadata layer for the Swift text worker.

This milestone is intentionally limited to:

- in-memory hot-tier cache metadata for one worker process
- prefix and block-table ownership in the worker
- cache stats and cache snapshot reporting through `CacheService.GetCacheStats`
- prefix pin and unpin support
- targeted hot-tier purge behavior

This milestone does **not** implement:

- disk-backed cache persistence
- restore flows
- checkpoint or snapshot save and restore
- cross-process cache reuse
- control-plane cache-aware scheduling

Those remain for later `Phase 3` milestones.

## Goal

Make the Swift text worker expose real hot-tier cache metadata instead of placeholder zero-value cache responses.

## Scope

Files expected to change:

- `services/mlx-text-worker-swift/Sources/Core/*`
- `services/mlx-text-worker-swift/Tests/CoreTests/*`
- `docs/README.md`

## Design

- Add a worker-local hot cache store that tracks:
  - cache scope
  - cache key
  - prefix refs
  - block tables
  - pinned state
  - reuse counters
- Register hot-tier cache metadata when `Prefill` succeeds and returns a decode handle.
- Reuse an existing hot prefix when the same cache key appears again in the same worker.
- Expose:
  - `CacheService.GetCacheStats`
  - `CacheService.PinPrefix`
  - `CacheService.UnpinPrefix`
  - `CacheService.PurgeCache`
- Keep:
  - `SaveBoundarySnapshot`
  - `RestoreBoundarySnapshot`
  as explicit structured `unimplemented` responses until later milestones.

## Performance Probes

This milestone must record or expose:

- `swift_text.cache_l1_bytes`
- `swift_text.cache_block_count`
- `swift_text.cache_prefix_count`
- `swift_text.cache_pinned_prefix_count`
- `swift_text.cache_l1_hit_rate`
- `swift_text.cache_block_reuse_ratio`

## Verification

Required commands:

```bash
make swift-test
make py-test
make integration-test
make coverage
git diff --check
```

## Acceptance

- `Prefill` returns a typed block table for hot-tier reuse metadata.
- `GetCacheStats` returns real hot-tier stats and snapshot content.
- `PinPrefix`, `UnpinPrefix`, and `PurgeCache` are implemented for the in-memory hot tier.
- The touched scope remains at or above `95%` measured coverage.
- The metrics report for this milestone includes real hot-tier cache counters, not `N/A`.
