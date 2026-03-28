# P2-M2 Scheduler Lane Read Model Plan

**Goal:** Land the first real control-plane scheduler slice by adding a lane-aware scheduler read model, explicit admission decisions, request progress snapshots, and queue-state reporting, while preserving the Phase 1 execution path and public HTTP behavior.

**Architecture:** This slice is control-plane-first. Melix keeps the current single active text execution path, but replaces implicit single-flight gating with an explicit scheduler read model that understands Phase 2 lane identities, records admit and reject decisions, publishes request-progress events, and surfaces queue-state snapshots through the control plane.

**Tech Stack:** Swift 6, Swift Package Manager, SwiftProtobuf-generated control-plane types, XCTest, existing control-plane and HTTP integration harnesses.

## Non-Goals

- Implement real queued execution or lane draining.
- Implement worker-side `Prefill` or `Decode`.
- Change the public HTTP contract for chat requests.
- Add background-lane execution for non-text families.

## Context

- Relevant specs:
  - `docs/architecture-spec.md`
  - `docs/control-plane-protocol.md`
  - `docs/plans/2026-03-27-phase-2-text-runtime-depth.md`
  - `docs/plans/2026-03-28-p2-m1-phase-aware-protocol-shapes.md`
- Relevant code paths:
  - `services/control-plane-swift/Sources/Requests/RequestCoordinator.swift`
  - `services/control-plane-swift/Sources/Snapshots/ServerSnapshotBuilder.swift`
  - `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
  - `services/control-plane-swift/Sources/Bootstrap/main.swift`
  - `services/control-plane-swift/Tests/ControlPlaneTests`
  - `services/control-plane-swift/Tests/HTTPGatewayTests`

## Assumptions

- Phase 1 remains the active live behavior: at most one active text request is admitted at a time.
- This slice should make scheduler state explicit without yet changing the execution model from reject-on-contention to queue-and-run-later.
- Request progress must become visible to the control plane even before real `Prefill` and `Decode` land.

## Performance Probes and Metrics

Required probes introduced or wired in this slice:

- `scheduler.admission_latency_ms`
- `scheduler.rejected_requests`
- `scheduler.active_lane_depth`
- `scheduler.backpressure`

Metrics report requirements:

- live queue delay remains `N/A`, because this slice does not yet implement queued execution
- admission, rejection, and snapshot visibility must be test-covered

## Work Plan

### Task 1: Add scheduler read-model state

**Objective**

Create an actor-backed scheduler read model that owns lane definitions, queue-summary state, and request-progress snapshots.

**Files**

- `services/control-plane-swift/Sources/EnginePool/*`
- `services/control-plane-swift/Tests/ControlPlaneTests/*`

**Implementation**

- add canonical lane definitions for:
  - `text.decode.interactive`
  - `text.prefill.hot`
  - `text.prefill.background`
- track admitted and rejected counts, active request ownership, lane-level backpressure, and last progress by request id
- expose queue-summary and request-progress snapshot accessors for other control-plane components

### Task 2: Replace implicit single-flight gating with explicit admission decisions

**Objective**

Make `RequestCoordinator` use the scheduler read model when requests are admitted, rejected, canceled, completed, or failed.

**Files**

- `services/control-plane-swift/Sources/Requests/RequestCoordinator.swift`
- `services/control-plane-swift/Tests/HTTPGatewayTests/RequestCoordinatorTests.swift`

**Implementation**

- record admitted requests with lane, priority, worker id, and admission latency
- record rejected requests when the current single-active policy blocks admission
- record terminal completion, abort, and failure states as request-progress snapshots
- preserve existing HTTP-visible behavior for Phase 1 callers

### Task 3: Surface scheduler state through snapshots and event fanout

**Objective**

Make scheduler state visible through control-plane snapshot reads and event subscriptions.

**Files**

- `services/control-plane-swift/Sources/Snapshots/ServerSnapshotBuilder.swift`
- `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- `services/control-plane-swift/Sources/Bootstrap/main.swift`
- `services/control-plane-swift/Tests/ControlPlaneTests/*`

**Implementation**

- build server snapshots from live scheduler-state data rather than static queue placeholders
- publish `request.progress` events through the existing event hub when scheduler state changes
- wire one shared scheduler read model through bootstrap so HTTP and XPC paths observe the same state

## Verification

```bash
make swift-test
make py-test
make integration-test
make coverage
```

## Acceptance

- the control plane exposes live lane and admission state through server snapshots
- request progress is published for admitted, rejected, completed, aborted, and failed states
- existing Phase 1 chat behavior remains stable
- touched scope stays at or above `95%` measured coverage
