# M9.4 Persistent Sessions And Remember-Me Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistent operator-auth session support and remember-me behavior so Melix can restore approved authenticated access after restart without conflating it with model session-graph state.

**Architecture:** Store remember-me session records separately from request or branch snapshots, attach them to the gateway access layer, and restore only policy-approved, non-expired auth sessions at startup. Keep session persistence deterministic, operator-visible, and revocable through explicit sign-out or retention expiry.

**Tech Stack:** Swift 6, SwiftUI, XCTest, integration tests, repository-owned smoke scripts and runbooks.

---

## Scope Notes

- Persistent auth sessions are distinct from `SessionGraphStore` request history and must not reuse that storage.
- Remember-me must be configurable, revocable, and TTL-bound.
- Store only the minimum session material needed for authenticated resume; keep secret serialization and rotation semantics explicit.

## Performance Probes And Success Metrics

- `persistent_session.restore_success_rate`
- `persistent_session.expired_session_count`
- `persistent_session.sign_out_latency_ms`
- `persistent_session.active_session_count`

## Task 1: Add Persistent Auth-Session Storage And Restore Policy

**Files:**
- Add: `services/control-plane-swift/Sources/HTTPGateway/OpenAI/PersistentAuthSessionStore.swift`
- Modify: `services/control-plane-swift/Sources/Bootstrap/main.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`

- [x] Define a typed persisted-auth-session record format with session ID, key ID, remember-me flag, creation time, expiry, and revocation metadata.
- [x] Add a bootstrap restore path that loads non-expired session records, drops stale ones, and publishes effective remembered-session state through control-plane snapshot metadata.
- [x] Keep persistent auth-session bookkeeping separate from model or request session state and reject malformed or expired records deterministically.
- [x] Add failing and then passing tests for restore success, expiry pruning, malformed-record isolation, and explicit revocation.

## Task 2: Enforce Remember-Me Semantics In The Gateway

**Files:**
- Modify: `services/control-plane-swift/Sources/HTTPGateway/OpenAI/GatewayAccessPolicy.swift`
- Modify: `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`
- Modify: `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`
- Add: `tests/integration/test_persistent_sessions.py`

- [x] Add remember-me login and restore semantics to the gateway access layer so approved sessions can be resumed after restart while non-remembered sessions expire on process exit.
- [x] Return structured session-state metadata in authorization failures and restore responses so clients can distinguish expired, revoked, and missing sessions.
- [x] Add failing and then passing handler and integration tests for remember-me restore, non-persistent session invalidation, expired-session rejection, and sign-out cleanup.
- [x] Record `persistent_session.restore_success_rate`, `persistent_session.expired_session_count`, and `persistent_session.active_session_count`.

## Task 3: Surface Remember-Me State And Runbook Guidance

**Files:**
- Modify: `apps/macos-menubar/Sources/AppMain/Models/DesktopShellState.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`
- Add: `docs/runbooks/persistent-sessions.md`
- Add: `scripts/m9_persistent_session_smoke.py`

- [x] Extend operator state so the shell can show active remembered sessions, retention policy, and sign-out status without exposing raw secrets.
- [x] Add operator copy and inspection guidance for session restore, revocation, and retention expiry.
- [x] Add a deterministic smoke script and runbook for remember-me restore, expiry, and logout paths.

## Verification And Commit Gate

- [x] Run targeted verification:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'PersistentAuthSessionStoreTests|OpenAIHandlerTests|ControlPlaneServiceTests'`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'PersistentAuthSessionStoreTests|OpenAIHandlerTests|ControlPlaneServiceTests'`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --scratch-path "$(pwd)/.build/menubar-scratch" --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --scratch-path "$(pwd)/.build/menubar-coverage" --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest tests/integration/test_persistent_sessions.py -q`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest tests/test_m9_persistent_session_smoke.py -q`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/m9_persistent_session_smoke.py --json`
- [x] Measure changed-line coverage for the touched Swift and integration scope and confirm coverage is at least `95%`.
- [x] Record the changed-scope metrics report for `persistent_session.restore_success_rate`, `persistent_session.expired_session_count`, `persistent_session.sign_out_latency_ms`, and `persistent_session.active_session_count`.
- [ ] Commit Task 4:
  - `git add services/control-plane-swift/Sources/HTTPGateway/OpenAI/PersistentAuthSessionStore.swift services/control-plane-swift/Sources/Bootstrap/main.swift services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Sources/HTTPGateway/OpenAI/GatewayAccessPolicy.swift services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift tests/integration/test_persistent_sessions.py apps/macos-menubar/Sources/AppMain/Models/DesktopShellState.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift docs/runbooks/persistent-sessions.md scripts/m9_persistent_session_smoke.py docs/plans/2026-03-30-m9-4-persistent-sessions-and-remember-me.md`
  - `git commit -m "feat: add persistent auth sessions and remember me"`

## Outcome

- Added repository-owned persistent gateway auth sessions with remember-me restore, structured session-state gateway errors, menu bar operator projection, and runbook guidance.
- Verification passed with the following changed-line coverage:
  - control-plane executable scope: `99.15%` (`1047/1056`)
  - menu bar executable scope: `100.00%` (`183/183`)
  - Python integration and smoke scope: `95.48%` (`190/199`)
  - aggregate touched executable scope: `98.75%` (`1420/1438`)
