# M13.1 Gateway Config State Model And Persistence

## Goal

Define the typed gateway-configuration model and persistence flow used by the control plane and desktop shell.

## Scope

- add typed gateway-config fields and merge behavior
- persist config through supported control-plane paths
- keep effective settings inspectable after resolution

## Files

- update `packages/protocol/schema/controlplane/v1/`
- update `services/control-plane-swift/Sources/HTTPGateway/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `apps/macos-menubar/Sources/AppMain/`

## Implementation Notes

- Persistence should preserve explicit operator edits and config-file imports.
- Effective settings should stay visible after precedence resolution.
- Config fields must remain reusable across API and desktop surfaces.

## Verification

- `make proto`
- `make swift-test`

## Acceptance

- Gateway configuration is typed, persistent, and inspectable through supported product surfaces.
