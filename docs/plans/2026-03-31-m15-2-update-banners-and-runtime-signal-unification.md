# M15.2 Update Banners And Runtime Signal Unification

## Goal

Unify update availability and runtime-state messaging so the desktop shell shows accurate, dismissible signals from control-plane truth.

## Scope

- add update-availability banners
- unify runtime and session signal messaging
- keep dismissal state consistent with product policy

## Files

- update `apps/macos-menubar/Sources/AppMain/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `tests/integration/`

## Implementation Notes

- Banner rendering should derive from explicit update and runtime state rather than heuristic polling.
- Dismissal state should not hide critical failure signals unintentionally.
- Runtime-signal copy should remain consistent across dashboard, chat, and status-bar surfaces.

## Verification

- `make swift-test`
- `make integration-test`

## Acceptance

- Update banners and runtime signals are accurate, dismissible where appropriate, and test-covered.
- Signal logic remains aligned across supported desktop surfaces.
