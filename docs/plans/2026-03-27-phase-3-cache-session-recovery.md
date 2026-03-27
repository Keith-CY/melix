# Phase 3 Unified Cache, Session Graph, and Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make unified cache reuse, session lineage, and live recovery first-class so that Melix can accelerate follow-ups, preserve branch-aware state, and resume work across tool boundaries instead of treating reuse as a best-effort optimization.

**Architecture:** Melix keeps cache metadata, session graph truth, and recovery policy in the Swift control plane while allowing workers to own runtime-local block materialization and snapshot payload handling. Reuse becomes an explicit control-plane feature built on cache keys, block tables, snapshot references, branch-aware session state, hot in-memory prefix or paged cache, disk-backed block persistence, and storage-boundary cache quantization rather than implicit prompt similarity.

**Tech Stack:** Swift 6, Swift Package Manager, MLX Swift bindings, gRPC over Unix Domain Sockets, SwiftProtobuf-generated protocol artifacts, XCTest, integration tests under `tests/integration`.

---

## Goal

Deliver a production-shaped Phase 3 implementation that introduces visible cache metadata, branch-aware session state, and resumable checkpoint or snapshot flow for the text runtime while preserving control-plane ownership of orchestration truth.

## Non-Goals

- Add new public API families beyond the text surfaces already in scope.
- Build L3 or remote cache layers.
- Generalize recovery to multimodal, embedding, rerank, or image workloads.
- Implement rich cache inspector UI beyond what is needed to prove the backend contract.
- Hide recovery or reuse behind opaque heuristics without observable control-plane state.
- Add full HuggingFace, quantization, or training workflows beyond the cache and recovery surfaces they later depend on.

## Context

- Relevant specs:
  - `docs/architecture-spec.md`
  - `docs/control-plane-protocol.md`
  - `docs/worker-rpc-schema.md`
  - `docs/phase-roadmap.md`
  - `docs/plans/2026-03-27-phase-2-text-runtime-depth.md`
- Relevant code paths:
  - `services/control-plane-swift/Sources/Snapshots`
  - `services/control-plane-swift/Sources/Requests`
  - `services/control-plane-swift/Sources/EnginePool`
  - `services/mlx-text-worker-swift/Sources/Runtime`
  - `services/mlx-text-worker-swift/Sources/Engine`
  - `packages/protocol/schema/controlplane/v1/*.proto`
  - `packages/protocol/schema/worker/v1/*.proto`
  - `tests/integration`
- Current constraints:
  - Phase 2 only provides live request-local phased execution.
  - Session continuity and follow-up speedups are not yet backed by explicit cache or branch state.
  - The control-plane docs already describe cache refs and session graph concepts, but the implementation does not yet realize them.
  - The current cache plan is not yet explicit enough about hot-tier prefix or paged cache coexistence, disk restore, or cache-quantization boundaries.

## Assumptions

- Phase 2 has already established explicit `Prefill` and `Decode` lifecycle support.
- The Swift text worker can expose stable logical cache references without moving cache ownership into the control plane.
- Session and branch identity stay local-first and do not require remote synchronization in this phase.
- Recovery scope is initially limited to the text runtime and tool-boundary follow-up flows.
- Cache reuse should combine hot in-memory prefix or paged reuse with durable disk-backed restore rather than choosing only one pattern.

## Performance Probes and Metrics

Required probes:

- `cache.hit_rate`
- `cache.block_reuse_ratio`
- `cache.snapshot_save_ms`
- `cache.snapshot_restore_ms`
- `session.followup_ttft_delta_ms`
- `scheduler.prefix_affinity_hit_rate`
- `cache.memory_bytes`
- `cache.disk_bytes`
- `cache.l2_restore_hit_rate`
- `cache.compression_ratio`

Required comparison report:

- cold request vs same-session follow-up request
- same-branch follow-up vs cross-branch follow-up
- live request continuation vs snapshot restore path
- unquantized cache footprint vs quantized cache footprint

## Work Plan

### Task 1: Finalize protocol support for cache, snapshots, and session graph state

**Objective**

Make cache references, block tables, snapshot refs, session branches, and resume metadata explicit in the shared protocol family.

**Files**

- Modify: `packages/protocol/schema/worker/v1/common.proto`
- Modify: `packages/protocol/schema/worker/v1/cache.proto`
- Modify: `packages/protocol/schema/controlplane/v1/control_plane.proto`
- Regenerate: `packages/protocol/swift/**/*`
- Regenerate: `packages/protocol/python/**/*`

**Implementation**

- Add or complete cache keys, block-table refs, snapshot refs, and cache statistics shapes.
- Add control-plane session and branch state with active branch and resume metadata.
- Keep payload ownership out of the control plane while making metadata observable and stable.

**Verification**

- `make proto`
- `swift build --package-path packages/protocol/swift`

**Acceptance**

- The protocol exposes cache and session graph state without collapsing runtime ownership boundaries.
- Generated artifacts remain aligned across Swift and Python.

### Task 2: Implement tiered cache metadata and snapshot primitives in worker runtimes

**Objective**

Give worker runtimes real cache-key tracking, hot-tier reuse, disk-backed block persistence, and save or restore primitives for text-only execution.

**Files**

- Modify: `services/mlx-text-worker-swift/Sources/Runtime/*`
- Modify: `services/mlx-text-worker-swift/Sources/Engine/*`
- Create or modify: `services/mlx-text-worker-swift/Sources/Cache/*`
- Modify tests under `services/mlx-text-worker-swift/Tests`

**Implementation**

- Track reusable prefix and block-table references for eligible requests.
- Add hot-tier prefix or paged cache behavior plus disk-backed block persistence where recovery policy requires it.
- Add cache quantization at the storage boundary so warm reuse and durable restore are measurable and space-aware.
- Add snapshot save and restore for tool-boundary and follow-up flows.
- Expose runtime stats for cache occupancy, reuse, and snapshot timing.
- Keep the first implementation local and conservative rather than overgeneralized.

**Verification**

- `swift test --package-path services/mlx-text-worker-swift`

**Acceptance**

- The worker can save, restore, and report cache-backed text state for supported request classes.
- Cache references remain stable enough for control-plane metadata tracking.

### Task 3: Implement session graph, branch lineage, and recovery policy in the control plane

**Objective**

Make session and branch state a first-class control-plane model instead of request-local convenience data.

**Files**

- Create or modify: `services/control-plane-swift/Sources/Snapshots/*`
- Create or modify: `services/control-plane-swift/Sources/Requests/*`
- Create or modify: `services/control-plane-swift/Sources/ModelCatalog/*`
- Modify tests under `services/control-plane-swift/Tests/ControlPlaneTests`

**Implementation**

- Add session state, branch lineage, active branch selection, and head-request tracking.
- Associate saved snapshots with request and branch context.
- Define explicit recovery rules for follow-ups, tool boundaries, and abandoned branches.
- Surface this state through existing control-plane query and event paths.

**Verification**

- `swift test --package-path services/control-plane-swift --filter ControlPlane`

**Acceptance**

- The control plane owns coherent session graph truth.
- Recovery behavior is explicit and test-covered rather than hidden in request translation.

### Task 4: Integrate cache-aware scheduling and follow-up acceleration

**Objective**

Turn cache metadata into real routing and scheduling decisions rather than passive reporting.

**Files**

- Modify: `services/control-plane-swift/Sources/EnginePool/*`
- Modify: `services/control-plane-swift/Sources/Requests/*`
- Modify: `services/control-plane-swift/Sources/Metrics/*`
- Modify related tests in `services/control-plane-swift/Tests`

**Implementation**

- Add prefix-affinity and reusable-state preference to admission decisions.
- Distinguish cold, warm, and restored request classes in the scheduler and metrics layer.
- Distinguish hot-memory, disk-restored, and quantized-cache restore paths in metrics and operator state.
- Ensure branch-aware follow-ups favor compatible state while keeping behavior deterministic.

**Verification**

- `make swift-test`
- `make integration-test`

**Acceptance**

- Same-session or same-branch follow-ups can realize measurable latency benefits.
- The scheduler can explain whether a request was cold, warm, or restored.

### Task 5: Add recovery-focused integration evidence and operator workflows

**Objective**

Leave Phase 3 with reproducible proof that cache reuse and recovery are real product behaviors rather than synthetic benchmarks.

**Files**

- Create or modify integration tests under `tests/integration`
- Modify: `scripts/dev_up.sh`
- Modify: `scripts/dev_down.sh`
- Create or modify: `docs/runbooks/*`

**Implementation**

- Add integration cases for same-session follow-up reuse, branch-aware divergence, snapshot restore, disk-backed restore, and explicit cold-path fallback.
- Add operator workflow documentation for observing cache state and validating restore behavior locally.
- Standardize the metrics report format for hit rate, reuse ratio, restore latency, compression ratio, and TTFT deltas.

**Verification**

- `make swift-test`
- `make py-test`
- `make integration-test`
- `make coverage`

**Acceptance**

- Integration tests cover reuse and restore behavior explicitly.
- The touched scope meets the `>=95%` coverage rule.
- The Phase 3 metrics report contains non-`N/A` cache and recovery numbers.

## Verification

```bash
make proto
swift test --package-path services/mlx-text-worker-swift
make swift-test
make py-test
make integration-test
make coverage
```

Expected evidence:

- cache and session protocol changes generate successfully
- the Swift text worker passes cache or snapshot tests
- the control plane passes session graph and scheduling tests
- integration proves follow-up acceleration and restore behavior
- touched-scope coverage is at least `95%`
- the metrics report includes hit rate, restore latency, compression ratio, and TTFT deltas

## Acceptance Criteria

- Melix exposes stable cache metadata, block tables, snapshot refs, and session graph state.
- Same-session and same-branch follow-ups show measurable acceleration over cold runs.
- Tool-boundary recovery can restore valid text-runtime state.
- Cache-aware scheduling and prefix affinity are real routing inputs rather than passive metadata.
- Phase 3 concludes with reproducible reuse, restore, and cache-tier evidence.

## Rollback or Safe Exit

- Land protocol, worker, control-plane, and integration slices separately so the repo stays bootable after each merge.
- Keep cold-path execution valid until restore behavior is fully verified.
- If snapshot or branch recovery proves unstable, stop at metadata visibility plus cold-path fallback rather than shipping misleading partial recovery.
