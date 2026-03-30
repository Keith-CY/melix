# M10.3 Desktop Status Banners And Operator Surfaces

## Goal

Surface session lifecycle and power state clearly in the desktop shell and chat-facing views.

## Scope

- add status banners for loading, sleeping, paused, and stopped states
- expose power-policy controls in settings or runtime surfaces
- keep UI copy grounded in control-plane truth

## Files

- update `apps/macos-menubar/Sources/AppMain/`
- update `apps/macos-menubar/Tests/MenuBarTests/`
- update `services/control-plane-swift/Sources/XPCService/`

## Implementation Notes

- Banner visibility must derive from live session-state events.
- Controls should stay disabled or hidden when policy or runtime state makes them invalid.
- Desktop hydration should preserve banner state across reconnects.

## Verification

- `make swift-test`

## Acceptance

- Desktop surfaces show lifecycle banners accurately.
- Operator controls and banner rendering are UI-test-covered.
