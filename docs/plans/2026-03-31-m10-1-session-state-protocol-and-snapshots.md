# M10.1 Session State Protocol And Snapshots

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
- `make swift-test`

## Acceptance

- Session-state protocol changes are typed, explicit, and test-covered.
- Snapshot and event consumers can represent the new lifecycle states without placeholders.
