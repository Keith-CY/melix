# M1.9 Desktop Residency And Memory UI

## Goal

Expose residency, eviction, and memory-protection state in the desktop operator surface so runtime decisions are understandable and actionable.

## Scope

- add residency and memory indicators to the operator UI
- surface eviction reasons and guard failures
- keep the UI driven by control-plane truth rather than UI-local inference

## Files

- update `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- update `apps/macos-menubar/Sources/AppMain/Dashboard/`
- update `apps/macos-menubar/Tests/MenuBarTests/`
- update `services/control-plane-swift/Sources/XPCService/`

## Implementation Notes

- UI should distinguish warm, pinned, evicting, and blocked states
- memory-protection failures should be visible without forcing log inspection
- avoid introducing desktop-only residency semantics that differ from HTTP and XPC snapshots

## Verification

- `make swift-test`
- `make integration-test`

## Acceptance

- the desktop shell can display residency and memory state for primary operator workflows
- desktop tests cover state transitions and operator-visible failure cases
