# P3-M4 Session Graph State Implementation Plan

**Phase:** Phase 3 Unified Cache, Session Graph, and Recovery  
**Milestone:** `P3-M4`  
**Status:** Planned

## Goal

Turn the control-plane session graph into a mutable source of truth instead of a read-only snapshot store so Melix can track active branches, branch lineage, request heads, tool-boundary metadata, and resume snapshots coherently.

## Scope

This milestone covers:

- control-plane session lifecycle commands
- branch creation and active-branch transitions
- tool-boundary and resume metadata updates
- request-driven session hydration for requests that already carry session and branch identity
- typed session-state change events

This milestone does not cover:

- worker-side checkpoint restore execution
- cache-aware scheduling decisions
- public HTTP session APIs
- multimodal session semantics

## Context

Relevant references:

- `docs/architecture-spec.md`
- `docs/control-plane-protocol.md`
- `docs/plans/2026-03-27-phase-3-cache-session-recovery.md`
- `docs/plans/2026-03-28-post-phase-0-coding-milestones.md`

Primary code paths:

- `services/control-plane-swift/Sources/Snapshots/SessionGraphStore.swift`
- `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- `services/control-plane-swift/Sources/Requests/RequestCoordinator.swift`
- `services/control-plane-swift/Tests/ControlPlaneTests/*`
- `services/control-plane-swift/Tests/HTTPGatewayTests/*`

## Assumptions

- The protocol already exposes `CreateSession`, `CreateBranch`, `CloseSession`, `RegisterToolResult`, and `ResumeAfterTool`.
- Request identity may already include `session_id`, `branch_id`, and `parent_request_id`, even if the current public chat surface does not expose them yet.
- The control plane should be able to hydrate session state from request metadata without waiting for later recovery milestones.

## Performance Probes

This milestone is state-management heavy rather than runtime-heavy. The required probes are:

- `session_graph.session_count`
- `session_graph.branch_count`
- `session_graph.resume_snapshot_count`
- `session_graph.active_branch_changes`
- `session_graph.request_hydration_ms`

Required metrics report:

- state-only metrics are acceptable for this milestone
- cache hit, restore latency, and TTFT deltas remain owned by later Phase 3 milestones

## Work Plan

### Task 1: Expand `SessionGraphStore` into a mutable state machine

Implement session creation, branch creation, branch selection, request-head updates, tool-result updates, resume metadata updates, and session closure with typed errors and deterministic timestamps for tests.

### Task 2: Implement session commands in `ControlPlaneService`

Wire `session.create`, `session.create_branch`, `session.close`, `session.register_tool_result`, and `session.resume_after_tool` to the store and publish `session.state_changed` events.

### Task 3: Hydrate session state from request metadata

When a request already carries `session_id` and `branch_id`, let `RequestCoordinator` update session and branch request heads and latest metadata without changing the public HTTP surface.

### Task 4: Add coverage and metrics evidence

Add control-plane and request-coordinator tests for:

- session creation and branch lineage transitions
- active-branch updates
- tool-result and resume metadata hydration
- request-driven session hydration
- session state-change event publication

## Verification

```bash
swift test --package-path services/control-plane-swift --enable-code-coverage
make swift-test
make py-test
make integration-test
git diff --check
```

## Acceptance

- Session commands mutate real control-plane state.
- Session summaries and `session.get_state` reflect active branch, lineage, latest request, tool metadata, and resume metadata.
- Request-driven session hydration is test-covered.
- Touched control-plane scope remains at or above `95%` coverage.

## Rollback

If the mutable session graph destabilizes the request path:

- keep the protocol surface intact
- revert request-driven hydration first
- preserve read-only `session.get_state` and snapshot summaries while the mutation paths are corrected
