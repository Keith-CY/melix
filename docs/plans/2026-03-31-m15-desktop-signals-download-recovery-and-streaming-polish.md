# M15 Desktop Signals, Download Recovery, And Streaming Polish

## Goal

Complete the desktop-shell operator experience with clearer runtime signals, smoother token rendering, paused-download recovery, and more coherent status messaging for long-running local workflows.

## Scope

- add smoother token rendering
- add update and runtime banners
- restore paused downloads after shell restart
- improve queue and status-bar clarity
- keep product-shell placeholders grounded in real control-plane navigation

## Coverage

- typewriter-style token rendering using a smooth UI-side presentation layer
- dismissible update-availability banner
- paused-download recovery after reopening the window
- richer download-queue and status-bar messaging
- runtime and session banners grounded in live control-plane state
- product-shell placeholders that remain attached to real navigation and control-plane truth

## Execution Slices

- `M15.1` Token-stream presentation smoothing
- `M15.2` Update banners and runtime-signal unification
- `M15.3` Download-queue persistence and paused-download recovery
- `M15.4` Desktop polish integration evidence

## Files

- update `apps/macos-menubar/Sources/AppMain/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `services/control-plane-swift/Sources/HTTPGateway/`
- update `tests/integration/`
- update `docs/runbooks/`

## Implementation Notes

- UI-side token smoothing must never reorder, suppress, or invent streamed content.
- Download recovery should restore persisted queue state rather than recreating download jobs heuristically.
- Update and runtime banners should derive from explicit state and should preserve dismissal state only where product policy allows it.
- Placeholder tabs and future-facing navigation should continue to rely on control-plane data contracts instead of static mock state.

## Verification

- `make swift-test`
- `make integration-test`
- desktop-polish smoke command for the touched scope

## Acceptance

- Token-render polish preserves content fidelity while improving perceived smoothness.
- Paused downloads can be restored after restarting the desktop shell.
- Update, queue, and runtime signals are accurate, dismissible where appropriate, and test-covered.
