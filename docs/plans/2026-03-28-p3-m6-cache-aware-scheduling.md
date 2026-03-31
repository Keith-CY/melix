# P3-M6 Cache-Aware Scheduling Plan

**Goal:** Turn Phase 3 cache metadata into real control-plane routing, admission, and observability decisions so that same-session or restored follow-ups prefer warm paths, expose prefix-affinity and cache-pressure state, and demonstrate measurable TTFT improvement over cold baselines.

**Architecture:** This slice stays control-plane-led. Melix keeps cache payload ownership in the Swift text worker, but the Swift control plane now consumes worker runtime and cache stats, classifies incoming requests as cold, warm, or restored, prefers hot-prefill lanes when reusable state exists, and records cache-aware metrics plus server-visible cache summaries.

**Tech Stack:** Swift 6, Swift Package Manager, gRPC over Unix Domain Sockets, SwiftProtobuf-generated protocol types, XCTest, Python integration tests under `tests/integration`.

## Non-Goals

- Add new public HTTP endpoints.
- Change worker cache persistence formats.
- Generalize cache-aware routing to Python multimodal workers.
- Add a desktop cache inspector UI.
- Implement full queue draining or multi-worker prefix placement.

## Context

- Relevant specs:
  - `docs/architecture-spec.md`
  - `docs/control-plane-protocol.md`
  - `docs/plans/2026-03-27-phase-3-cache-session-recovery.md`
  - `docs/plans/2026-03-28-post-phase-0-coding-milestones.md`
- Relevant code paths:
  - `services/control-plane-swift/Sources/Requests/*`
  - `services/control-plane-swift/Sources/EnginePool/*`
  - `services/control-plane-swift/Sources/Snapshots/*`
  - `services/control-plane-swift/Sources/WorkerClient/*`
  - `services/mlx-text-worker-swift/Sources/Core/*`
  - `tests/integration`

## Assumptions

- Session graph and snapshot restore are already live from `P3-M4` and `P3-M5`.
- The Swift text worker already reports cache stats and runtime stats through existing worker RPCs.
- A follow-up request can be considered warm when it has compatible branch state or prefix affinity, even if it is not a full snapshot restore.
- Deterministic backend behavior may be tuned to make warm or restored paths reproducibly faster, while the real MLX backend keeps its existing semantics.

## Performance Probes and Metrics

Required probes introduced or wired in this slice:

- `scheduler.prefix_affinity_hit_rate`
- `scheduler.warm_route_preference_rate`
- `scheduler.restored_route_rate`
- `scheduler.cache_pressure`
- `cache.memory_bytes`
- `cache.disk_bytes`
- `cache.hit_rate`
- `cache.l2_restore_hit_rate`
- `cache.compression_ratio`
- `session.followup_ttft_delta_ms`

Metrics report requirements:

- report cold-path TTFT and warm or restored follow-up TTFT for the same session flow
- report whether the request was classified as `cold`, `warm`, or `restored`
- report cache occupancy and restore-hit metrics from the Swift text worker

## Work Plan

### Task 1: Add worker introspection and control-plane cache metadata refresh

**Objective**

Let the control plane pull cache and runtime stats from the Swift text worker and mirror them into control-plane metrics and cache snapshots.

**Files**

- `services/control-plane-swift/Sources/WorkerClient/*`
- `services/control-plane-swift/Sources/Snapshots/*`
- `services/control-plane-swift/Sources/Bootstrap/main.swift`

**Implementation**

- extend the Swift text worker client surface with runtime-stats and cache-stats helpers
- share one `CacheMetadataStore` between bootstrap, request coordination, and XPC snapshot serving
- map worker cache stats into control-plane cache summaries and resource-oriented metrics

### Task 2: Classify requests as cold, warm, or restored and prefer hot routes

**Objective**

Make request coordination explicitly cache-aware instead of treating all text requests as equal.

**Files**

- `services/control-plane-swift/Sources/Requests/RequestCoordinator.swift`
- `services/control-plane-swift/Sources/Snapshots/SessionGraphStore.swift`
- `services/control-plane-swift/Sources/EnginePool/*`

**Implementation**

- inspect session graph state, restore hints, and head cache keys before admission
- classify each request as `cold`, `warm`, or `restored`
- route warm or restored phase-aware requests through `text.prefill.hot`
- route cold phase-aware requests through `text.prefill.background`
- record prefix-affinity hits and warm-route preferences in control-plane metrics
- propagate head cache keys from phase-aware prefill results back into session graph state

### Task 3: Record TTFT deltas and recovery-aware evidence

**Objective**

Make the follow-up speed benefit measurable and reproducible.

**Files**

- `services/control-plane-swift/Sources/Requests/RequestCoordinator.swift`
- `services/mlx-text-worker-swift/Sources/Core/Runtime/DeterministicTextBackend.swift`
- `services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift`
- `tests/integration/*`

**Implementation**

- record cold TTFT baselines per session and branch
- record warm or restored TTFT and compute `session.followup_ttft_delta_ms`
- measure the follow-up delta from request-coordination start rather than dispatch-only timing so warm-path gains that happen before worker dispatch remain visible
- make deterministic restore paths faster than cold baselines in a stable, explicit way
- add integration evidence for warm-route preference and measurable follow-up gain

## Verification

```bash
make swift-test
make py-test
make integration-test
make coverage
git diff --check
```

## Acceptance

- the control plane exposes live cache occupancy and hit-rate metrics from the Swift text worker
- same-session or restored follow-ups are classified as warm or restored and routed through hot-prefill preference
- prefix-affinity and warm-route preference metrics are non-zero in the relevant follow-up paths
- follow-up TTFT improvement versus a cold baseline is measured and non-`N/A`
- touched scope stays at or above `95%` measured coverage
