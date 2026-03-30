# M1.9 Desktop Residency And Memory UI

## Goal

Expose residency, eviction, and memory-protection state in the desktop operator surface so runtime decisions are understandable and actionable.

## Scope

- add residency and memory indicators to the operator UI
- surface eviction reasons and guard failures
- keep the UI driven by control-plane truth rather than UI-local inference

## Files

- update `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- update `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationState.swift`
- update `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift`
- update `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`
- update `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`

## Implementation Notes

- UI should distinguish warm, pinned, evicting, and blocked states
- memory-protection failures should be visible without forcing log inspection
- avoid introducing desktop-only residency semantics that differ from HTTP and XPC snapshots
- residency copy should fall back safely when snapshots omit newer residency fields
- dashboard summaries should derive from control-plane metrics first and use snapshot-model fallbacks second
- desktop view tests should cover both populated and empty residency sections so operator-facing alert paths stay stable

## Verification

- `swift test --package-path apps/macos-menubar --filter RuntimeViewModelTests`
- `swift test --package-path apps/macos-menubar --skip-build --filter DesktopFoundationViewTests`
- `swift test --package-path apps/macos-menubar --enable-code-coverage --filter RuntimeViewModelTests`
- `swift test --package-path apps/macos-menubar --enable-code-coverage --skip-build --filter DesktopFoundationViewTests`
- `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationState.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift`
- `git diff --check`

## Acceptance

- the desktop shell can display residency and memory state for primary operator workflows
- desktop tests cover state transitions and operator-visible failure cases
- residency dashboard cards summarize pinning, eviction, and memory-guard activity from control-plane truth
