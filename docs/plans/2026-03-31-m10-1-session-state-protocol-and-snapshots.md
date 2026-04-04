# M10.1 Session State Protocol And Snapshots

Status: completed.

## Goal

Define the protocol, snapshot, and event-model changes needed for explicit session lifecycle and power-state behavior.

## Scope

- add typed session-state and power-state fields
- expose wake reason, idle-timer, and auto-sleep metadata
- keep snapshot and event semantics aligned across XPC and API-facing views

## Files

- update `packages/protocol/schema/controlplane/v1/`
- update `services/control-plane-swift/Sources/Snapshots/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `apps/macos-menubar/Sources/AppMain/`

## Implementation Notes

- Snapshot state must distinguish `paused` from `sleeping`.
- Event payloads should be sufficient for banner rendering without local UI inference.
- Existing server-state fields should remain backward-compatible where possible.

## Verification

- `make proto`
- `swift test --package-path services/control-plane-swift --filter ControlPlaneServiceTests`
- `swift test --package-path apps/macos-menubar --filter RuntimeViewModelTests`
- `swift test --package-path services/control-plane-swift --enable-code-coverage`
- `make swift-test`
- focused Swift changed-line coverage for the touched handwritten executable scope is `100.00%`
  (`425/425`)

## Acceptance

- Session-state protocol changes are typed, explicit, and test-covered.
- Snapshot and event consumers can represent the new lifecycle states without placeholders.

## Outcome

- `ServerSessionRuntimeState` is now a dedicated control-plane protocol type for lifecycle,
  power-state, wake-reason, and idle-policy metadata, separate from the existing Phase 3
  branch/session graph contract.
- control-plane snapshots and `server.state_changed` events now project typed
  `runtime_sessions`, and the native menu bar client consumes that payload directly instead of
  inferring paused-versus-sleeping state locally.
