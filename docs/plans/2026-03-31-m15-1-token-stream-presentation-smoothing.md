# M15.1 Token-Stream Presentation Smoothing

## Goal

Improve perceived token streaming smoothness in the desktop shell without changing underlying content or event ordering.

## Scope

- add UI-side token presentation smoothing
- preserve exact runtime content fidelity
- keep stream metrics visible for regression detection

## Files

- update `apps/macos-menubar/Sources/AppMain/`
- update `apps/macos-menubar/Tests/MenuBarTests/`
- update `services/control-plane-swift/Sources/XPCService/`

## Implementation Notes

- Presentation smoothing must never invent, reorder, or suppress streamed tokens.
- The UI should remain resilient to reconnects, usage deltas, and terminal events.
- Regression detection should focus on lag and fidelity, not only animation behavior.

## Verification

- `make swift-test`

## Acceptance

- Token presentation is smoother while preserving exact streamed content.
- UI-side stream smoothing is test-covered.
