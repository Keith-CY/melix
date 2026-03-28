# P3-M3 Disk and Quantized Cache Tier Implementation Plan

**Goal:** Add a durable L2 cache tier for the Swift text worker so boundary snapshots can be saved, restored after worker restart, and measured with real quantized-footprint statistics instead of placeholder ratios.

**Architecture:** This milestone stays worker-local. The Swift text worker keeps L1 hot-prefix metadata in memory and adds a conservative file-backed L2 cache store for block-table metadata and snapshot records. The control plane continues to see only cache metadata through existing RPCs.

**Tech Stack:** Swift 6, Swift Package Manager, SwiftProtobuf, Foundation file I/O, XCTest.

## Goal

Deliver the first durable cache tier for the Swift text worker with:

- file-backed L2 cache metadata
- boundary snapshot save and restore RPCs
- restart-safe restore for deterministic text execution
- measurable `l2_bytes`, `snapshot_count`, `quantized_bytes`, `compression_ratio`, and `l2_restore_hit_rate`

## Non-Goals

- Control-plane session graph or branch lineage work
- Cache-aware scheduling or prefix-affinity routing
- Multimodal or Python-worker cache persistence
- Full MLX runtime state serialization beyond the conservative restore path used here

## Context

- Phase plan: `docs/plans/2026-03-27-phase-3-cache-session-recovery.md`
- Milestone ladder: `docs/plans/2026-03-28-post-phase-0-coding-milestones.md`
- Current worker cache code:
  - `services/mlx-text-worker-swift/Sources/Core/HotCacheStore.swift`
  - `services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift`
  - `services/mlx-text-worker-swift/Sources/Core/WorkerServices.swift`
  - `services/mlx-text-worker-swift/Sources/Core/Inference/TextPrefillEngine.swift`
  - `services/mlx-text-worker-swift/Sources/Core/Inference/TextDecodeEngine.swift`

## Assumptions

- The first durable restore path may conservatively rebuild runtime-local prefill context from persisted prompt metadata instead of serializing opaque runtime internals.
- Durable restore proof for this milestone is required on the deterministic backend; MLX parity can follow in later recovery milestones.
- Snapshot save and restore stay scoped to text-worker-local boundary snapshots keyed by `snapshot_id`.

## Performance Probes and Metrics

Required probes:

- `swift_text.cache_snapshot_save_ms`
- `swift_text.cache_snapshot_restore_ms`
- `swift_text.cache_l2_bytes`
- `swift_text.cache_snapshot_count`
- `swift_text.cache_quantized_bytes`
- `swift_text.cache_compression_ratio`
- `swift_text.cache_l2_restore_hit_rate`

Required comparison report:

- hot-tier-only prefill vs disk-backed restored prefill
- pre-restart snapshot availability vs post-restart snapshot restore
- unquantized block bytes vs storage-boundary quantized bytes

## Work Plan

### Task 1: Add durable L2 cache storage primitives

**Files**

- Create: `services/mlx-text-worker-swift/Sources/Core/DiskCacheStore.swift`
- Modify: `services/mlx-text-worker-swift/Sources/Core/WorkerConfiguration.swift`
- Modify: `services/mlx-text-worker-swift/Sources/Core/WorkerBootstrap.swift`

**Implementation**

- Add a worker configuration path for the Swift text worker cache root.
- Persist block-table metadata and snapshot records under a worker-local cache directory.
- Keep the file format simple and local-first.

**Acceptance**

- A fresh worker instance pointed at an existing cache root can discover L2 cache and snapshot metadata.

### Task 2: Wire save and restore through the runtime registry

**Files**

- Modify: `services/mlx-text-worker-swift/Sources/Core/HotCacheStore.swift`
- Modify: `services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift`
- Modify: `services/mlx-text-worker-swift/Sources/Core/WorkerServices.swift`

**Implementation**

- Persist eligible block-table records into L2 when a request asks for durable cache or when a snapshot is saved.
- Implement `SaveBoundarySnapshot` and `RestoreBoundarySnapshot`.
- Rebuild a decode-ready runtime context from persisted prompt metadata on restore.
- Surface real L2 and quantized-footprint stats through existing cache and runtime stats RPCs.

**Acceptance**

- Saving a boundary snapshot returns a real `snapshot_id`.
- Restoring that snapshot yields a usable `decode_handle`, `block_table_id`, and `block_table`.

### Task 3: Add durable-restore tests and metrics evidence

**Files**

- Modify: `services/mlx-text-worker-swift/Tests/CoreTests/WorkerScaffoldTests.swift`

**Implementation**

- Add worker tests for:
  - snapshot save
  - snapshot restore
  - restart-safe restore using a fresh registry against the same cache root
  - measurable L2 bytes and compression ratio
- Keep the deterministic backend as the proof path.

**Acceptance**

- Worker tests prove durable restore and non-placeholder cache metrics.
- Touched scope coverage remains at or above `95%`.

## Verification

```bash
make swift-test
make py-test
make integration-test
make coverage
git diff --check
```

## Metrics Report Requirements

This milestone must report:

- Swift text worker coverage
- cache snapshot save latency
- cache snapshot restore latency
- L2 bytes
- quantized bytes
- compression ratio
- L2 restore hit rate

`N/A` is not acceptable for the cache metrics in this milestone.
