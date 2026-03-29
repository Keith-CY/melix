# P8-M1 Native Operator Shell Completion

## Goal

Finish the remaining desktop-shell product slice for Phase 8 without pulling later diagnostics or training scope forward. This milestone hardens the native operator shell around connection health, bounded reconnect behavior, and richer dashboard or settings hydration from existing control-plane truth.

## Scope

- macOS operator-shell state and view hydration
- connection-health representation for the native shell
- bounded auto-reconnect when the control-plane subscription stream ends
- operator-visible recovery logs and metrics

## Non-Goals

- doctor, bench, or training workflows
- packaging, launchd, signing, or installer assets
- new backend capabilities that do not already exist in the control plane
- a second control plane inside the app

## Files

- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationState.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift`
- Modify: `docs/README.md`

## Desired Behavior

- The desktop shell exposes whether it is connecting, connected, reconnecting, or degraded.
- Unexpected subscription termination triggers a bounded reconnect attempt rather than silent staleness.
- Reconnect attempts reuse the last seen event sequence and append explicit operator logs.
- Dashboard and settings tabs surface connection-health rows derived from the live view-model state.
- The implementation does not duplicate control-plane state; it derives product state from the existing snapshot and subscription flow.

## Performance Probes

- `desktop.reconnect_attempt_ms`
- `desktop.reconnect_success_ms`
- `desktop.reconnect_failure_count`
- `desktop.connection_state_transitions`

## Test Plan

- Add failing `RuntimeViewModel` tests for subscription termination and reconnect hydration.
- Add failing view tests for connection-health rendering in the desktop shell.
- Run:
  - `swift test --package-path apps/macos-menubar --filter RuntimeViewModelTests`
  - `swift test --package-path apps/macos-menubar --filter DesktopFoundationViewTests`
  - `make coverage`
  - `git diff --check`

## Acceptance

- The operator shell no longer goes stale when the event stream ends unexpectedly.
- Connection health is visible in the native shell.
- Reconnect state is covered by app tests.
- Touched-scope coverage remains at or above `95%`.
