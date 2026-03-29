# M1.3 Worker Memory And Cache Accounting

## Goal

Extend worker-side runtime reporting so Melix can make admission, residency, and eviction decisions using real resident, KV, and cache memory evidence.

## Scope

- add stable memory-accounting fields to worker runtime stats
- distinguish model residency bytes from cache bytes and request-local spikes
- expose enough detail for later process-level memory enforcement

## Files

- update `packages/protocol/schema/worker/v1/`
- update `services/mlx-text-worker-swift/Sources/Core/`
- update `services/mlx-worker-python/worker/registry.py`
- update `services/mlx-worker-python/worker/runtime/`
- update `services/control-plane-swift/Sources/WorkerClient/`

## Implementation Notes

- keep the reporting schema shared across worker families even if some values are zero on day one
- include headroom and peak-allocation fields where they are needed for guards
- treat memory accounting as observable runtime truth rather than diagnostic-only metadata

## Verification

- `make proto`
- `make swift-test`
- `make py-test`

## Acceptance

- worker runtime stats expose resident, KV, cache, and peak-allocation fields
- control-plane logic can consume memory evidence without runtime-family-specific parsing
