# M8.7 Model Settings Completion

Status: completed in commit `feat: close M8.7 model settings completion`

## Goal

Complete the per-model settings surface so operators can manage aliasing, type override, fallback behavior, resource input, and merged sampling controls coherently.

## Scope

- complete the model-settings surface
- preserve non-destructive settings merging
- keep effective settings visible after policy resolution

## Files

- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- update `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- update `apps/macos-menubar/Tests/MenuBarTests/`

## Implementation Notes

- settings resolution should remain deterministic across defaults, registry metadata, and operator overrides
- fallback behavior should be explicit rather than inferred
- preserve room for generation-config import in the next slice

## Verification

- `make swift-test`
- `make integration-test`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/services/control-plane-swift/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'executeMapsAdaptiveThinkingAndParserFallbackModelPolicyValues|executeClearsTTLandAdaptiveThinkingBudgetsWhenDraftsAreEmpty'`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/apps/macos-menubar/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'modelsTabFormButtonsDispatchActions|modelInfoSummaryViewRendersTypedSettingsAndMergedDefaults|modelSettingsValidationGuardsInvalidDraftsResetsValuesAndNoOpsWithoutPrimaryModel|modelSettingsDraftsNormalizeUnknownResidencyAccelerationAndAdaptiveDefaults'`
- `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
- `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift`

## Acceptance

- the completed model-settings surface is operator-visible and test-covered
- effective settings can be inspected after merges and overrides

## Completion Notes

- completed the operator-visible per-model settings editor with typed controls for alias, type override, TTL, pin-on-load, memory policy, acceleration mode, acceleration profile, adaptive thinking, and parser fallback
- surfaced effective model settings, OCR prompt defaults, OCR sampling defaults, and OCR stop sequences through a shared model-info summary surface in both the model tools and workspace shell views
- preserved deterministic control-plane parsing for empty-string clears and typed adaptive-thinking policy fields
- changed-line coverage for the touched executable scope:
  - control-plane: `100.00% (49/49)`
  - menu bar: `97.36% (663/681)`
