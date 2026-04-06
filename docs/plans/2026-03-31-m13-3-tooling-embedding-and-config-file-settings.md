# M13.3 Tooling, Embedding, And Config-File Settings

## Status

Completed on 2026-04-06. Melix now projects typed tooling settings through the control-plane
snapshot, including embedding-model selection, preload state, tool-parser modes, MCP summary,
inspectable config-file location, and boot additional arguments, while the native desktop shell
renders the same settings from one repository-owned truth surface.

## Goal

Expose embedding-model selection, tool-parser settings, MCP configuration, config-file location, and additional-arguments handling through one coherent settings surface.

## Scope

- add embedding-model selection and preload settings
- expose tool-parser and MCP configuration
- expose config-file path and additional-arguments state

## Files

- update `services/control-plane-swift/Sources/XPCService/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `docs/runbooks/`

## Implementation Notes

- Config-file state should remain inspectable even when the current process inherited values at boot.
- MCP and parser settings should remain configuration-driven, not hardcoded in UI.
- Embedding selection must align with capability-aware model discovery.

## Executable Slices

### Slice 1: Typed Tooling Settings Summary

- add a typed `tooling_settings` summary to `ServerSnapshot`
- expose the active embedding model, backend family, and preload state
- expose built-in tool-parser modes, effective MCP summary, inspectable config paths, and boot
  additional arguments
- hydrate the desktop Tools > Settings surface from the typed summary

Status: completed on 2026-04-06.

## Verification

- `make proto`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'ControlPlaneServiceTests'`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'DesktopFoundationViewTests'`
- `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/HTTPGateway/OpenAI/GatewayConfigStore.swift services/control-plane-swift/Sources/HTTPGateway/OpenAI/GatewayServingDefaultsStore.swift services/control-plane-swift/Sources/Requests/ToolParserRegistry.swift services/control-plane-swift/Sources/Snapshots/ServerSnapshotBuilder.swift services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Sources/XPCService/ToolingSettingsSnapshotSource.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
- `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationState.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`
- `git diff --check`

Results:

- focused control-plane coverage suite: `159 tests in 1 suite passed`
- focused Window UI coverage suite: `64 tests in 1 suite passed`
- Swift control-plane changed-line coverage: `100.00%` (`83/83`)
- Swift menu-bar changed-line coverage: `100.00%` (`226/226`)
- aggregate touched-scope changed-line coverage: `100.00%` (`309/309`)
- `make swift-test` still fails outside the touched scope because
  `services/mlx-text-worker-swift` exits with signal `11` in `WorkerScaffoldTests`

## Acceptance

- Tooling, embedding, and config-file settings are visible, stable, and test-covered.
- Operators can inspect the effective settings path without reading source files.
