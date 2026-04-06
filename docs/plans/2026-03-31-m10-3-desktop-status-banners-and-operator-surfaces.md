# M10.3 Desktop Status Banners And Operator Surfaces

Status: completed on 2026-04-05. The desktop shell, server workspace, and chat-facing surfaces now
project control-plane-owned lifecycle and idle-policy truth through typed lifecycle banners, inline
notices, and session-scoped operator controls without relying on optimistic local lifecycle
transitions.

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
- The final desktop implementation keeps lifecycle banners authoritative by reading hydrated
  `ServerSessionRuntimeState` snapshots and later `server.state_changed` events while leaving
  lifecycle mutations to the control plane rather than applying optimistic menu-bar-local state
  changes.
- Operator surfaces now expose pause, resume, wake, stop, and idle-policy controls with
  deterministic enablement summaries shared between the dashboard and chat workspace.

## Verification

- `make swift-test`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|DesktopShellStateTests|ControlPlaneXPCClientTests'`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|DesktopShellStateTests|ControlPlaneXPCClientTests'`
- `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Chat/DesktopChatView.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Sources/AppMain/Models/DesktopShellState.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/ControlPlaneXPCClientTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopShellStateTests.swift`
- `git diff --check`

## Acceptance

- Desktop surfaces show lifecycle banners accurately.
- Operator controls and banner rendering are UI-test-covered.

## Verification Results

- `make swift-test`: pass
- focused menu bar lifecycle suites: `199 tests in 4 suites passed after 3.798 seconds`
- focused menu bar lifecycle suites with code coverage: `199 tests in 4 suites passed after 3.813 seconds`
- `git diff --check`: pass

## Metrics Report

- lifecycle interaction metrics emitted by the desktop shell:
  - `menu.server_start_ms`
  - `menu.server_pause_ms`
  - `menu.server_resume_ms`
  - `menu.server_wake_ms`
  - `menu.server_stop_ms`
  - `menu.server_idle_policy_ms`
- aggregate changed-line coverage for the touched handwritten menu bar Swift scope:
  `95.79%` (`1116/1165`)
