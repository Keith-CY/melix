# P2-M6 Abort and Phase Observability Implementation Plan

**Goal:** Make the Phase 2 text path observable and cancellable across queued, prefill, and decode states without widening the public API surface.

**Scope:** This milestone is limited to control-plane lifecycle tracking, phase-aware request progress, queued or active abort handling, and tests plus metrics for those paths. It does not yet add multi-request throughput benchmarks or queue-pressure operator workflows.

## Context

- Phase plan: `docs/plans/2026-03-27-phase-2-text-runtime-depth.md`
- Milestone ladder: `docs/plans/2026-03-28-post-phase-0-coding-milestones.md`
- Relevant code:
  - `services/control-plane-swift/Sources/EnginePool/SchedulerReadModel.swift`
  - `services/control-plane-swift/Sources/Requests/RequestCoordinator.swift`
  - `services/control-plane-swift/Sources/Requests/AbortRegistry.swift`
  - `services/control-plane-swift/Tests/ControlPlaneTests/*`
  - `services/control-plane-swift/Tests/HTTPGatewayTests/*`

## Non-Goals

- Build a true multi-request queue or queue-pressure benchmark harness.
- Add new HTTP endpoints, SSE event types, or desktop operator views.
- Change the worker protocol shapes introduced in `P2-M1`.
- Introduce cache persistence or restart-aware recovery.

## Performance Probes

- `scheduler.queue_delay_ms`
- `scheduler.active_lane_depth`
- `swift_text.abort_queued_ms`
- `swift_text.abort_prefill_ms`
- `swift_text.abort_decode_ms`
- `http.abort_ms`

## Work Plan

### Task 1: Persist queued state and queue-delay evidence in the scheduler read model

- Add an explicit queued transition before admission.
- Preserve per-request queue timing so admitted progress can report a real `queue_delay_ms`.
- Update lane summaries so queued and active counts reflect the current lifecycle phase.

### Task 2: Promote request progress from admitted-only to phase-aware transitions

- Record control-plane request lifecycle transitions for `queued`, `prefilling`, `decoding`, and terminal states.
- Allow active-lane attribution to move from the decode lane into the hot-prefill lane and back again.
- Preserve acceleration and decode-handle metadata where the worker exposes it.

### Task 3: Support queued and phase-specific abort semantics in the request coordinator

- Allow cancellation before a worker has been bound to a live request.
- Distinguish queued, prefill, and decode abort metrics.
- Preserve abort continuity across phase-aware prefill-to-decode handoff so a live request does not expose a false-negative abort gap while decode admission is starting.
- Keep existing public behavior stable for admitted and streaming requests.

### Task 4: Add red-green coverage for queued, prefill, and decode observability

- Cover queued progress and queue-delay snapshots.
- Cover worker-event-driven transitions into prefill and decode phases.
- Cover queued abort without a bound worker and phase-specific abort metrics once a worker is active.

## Verification

```bash
swift test --package-path services/control-plane-swift
make swift-test
make py-test
make integration-test
make coverage
git diff --check
```

## Acceptance

- Scheduler snapshots expose queued, admitted, prefill, decode, and terminal request evidence.
- Cancellation succeeds both before and after worker binding, with phase-specific metrics recorded.
- Phase-aware text requests remain abortable through the prefill-to-decode transition without relying on client-side retries.
- The changed control-plane scope remains at or above `95%` measured coverage.
