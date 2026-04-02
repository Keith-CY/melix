# M9.6 Connection Lifecycle Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden Melix connection lifecycle behavior so streaming and long-running operator sessions can detect disconnects, retry safely, resume deterministically, and emit measurable keepalive and recovery signals.

**Architecture:** Build on the existing SSE keepalive and request-coordinator disconnect hooks, add an explicit lifecycle policy object, and drive retry or resume behavior from the control plane instead of ad hoc caller-side assumptions. Keep disconnect classification, resume eligibility, and keepalive cadence observable through tests and metrics.

**Tech Stack:** Swift 6, XCTest, integration tests, repository-owned smoke scripts and runbooks.

---

## Scope Notes

- Reuse the existing `SSEStreamWriter`, `RequestCoordinator`, and `SessionGraphStore` foundations rather than replacing the streaming stack.
- Distinguish transient disconnects from terminal request failure and from explicit operator cancellation.
- Resume must preserve session and branch identity instead of spawning silent replacement sessions.

## Performance Probes And Success Metrics

- `disconnect.recovery_latency_ms`
- `disconnect.resume_success_rate`
- `disconnect.keepalive_gap_ms`
- `disconnect.terminal_failure_count`

## Task 1: Add Explicit Connection Lifecycle Policy

**Files:**
- Add: `services/control-plane-swift/Sources/HTTPGateway/SSE/ConnectionLifecyclePolicy.swift`
- Modify: `services/control-plane-swift/Sources/HTTPGateway/SSE/SSEStreamWriter.swift`
- Modify: `services/control-plane-swift/Sources/Requests/RequestCoordinator.swift`
- Modify: `services/control-plane-swift/Tests/HTTPGatewayTests/SSEStreamWriterTests.swift`
- Modify: `services/control-plane-swift/Tests/HTTPGatewayTests/RequestCoordinatorTests.swift`

- [ ] Define typed lifecycle policy for keepalive cadence, disconnect grace period, retry eligibility, and resume eligibility.
- [ ] Apply that policy in `SSEStreamWriter` and `RequestCoordinator` so disconnect callbacks, keepalive emission, and request cleanup behave consistently across endpoints.
- [ ] Add failing and then passing tests for keepalive interval enforcement, transient disconnect cleanup, explicit cancellation non-resume behavior, and resume-eligible session preservation.
- [ ] Record `disconnect.keepalive_gap_ms` and `disconnect.terminal_failure_count`.

## Task 2: Add Integration Recovery Paths And Observable Resume State

**Files:**
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneChatExecution.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `tests/integration/test_recovery_flows.py`
- Add: `tests/integration/test_connection_lifecycle.py`

- [ ] Surface connection lifecycle state through control-plane execution bookkeeping so callers can distinguish resumed, retrying, aborted, and terminally failed requests.
- [ ] Add live integration coverage for disconnect-and-resume, keepalive timeout, and retry-to-terminal-failure paths using the deterministic local stack.
- [ ] Measure and report `disconnect.recovery_latency_ms` and `disconnect.resume_success_rate`.

## Task 3: Add Runbook And Smoke Validation

**Files:**
- Add: `docs/runbooks/connection-lifecycle.md`
- Add: `scripts/m9_connection_smoke.py`

- [ ] Add a deterministic smoke script that exercises keepalive-only, disconnect-resume, and terminal-failure paths and emits machine-readable recovery metrics.
- [ ] Document expected keepalive policy, retry limits, resume prerequisites, and operator troubleshooting steps for stuck streams and stalled recoveries.
- [ ] Capture a metrics report for the changed scope and explicitly note any remaining known blockers.

## Verification And Commit Gate

- [ ] Run targeted verification:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'SSEStreamWriterTests|RequestCoordinatorTests|ControlPlaneServiceTests'`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest tests/integration/test_recovery_flows.py tests/integration/test_connection_lifecycle.py -q`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/m9_connection_smoke.py --json`
- [ ] Measure changed-line coverage for the touched Swift and integration scope and confirm coverage is at least `95%`.
- [ ] Record the changed-scope metrics report for `disconnect.recovery_latency_ms`, `disconnect.resume_success_rate`, `disconnect.keepalive_gap_ms`, and `disconnect.terminal_failure_count`.
- [ ] Commit Task 6:
  - `git add services/control-plane-swift/Sources/HTTPGateway/SSE/ConnectionLifecyclePolicy.swift services/control-plane-swift/Sources/HTTPGateway/SSE/SSEStreamWriter.swift services/control-plane-swift/Sources/Requests/RequestCoordinator.swift services/control-plane-swift/Sources/XPCService/ControlPlaneChatExecution.swift services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Tests/HTTPGatewayTests/SSEStreamWriterTests.swift services/control-plane-swift/Tests/HTTPGatewayTests/RequestCoordinatorTests.swift tests/integration/test_recovery_flows.py tests/integration/test_connection_lifecycle.py docs/runbooks/connection-lifecycle.md scripts/m9_connection_smoke.py docs/plans/2026-03-30-m9-6-connection-lifecycle-hardening.md`
  - `git commit -m "feat: harden connection lifecycle recovery"`
