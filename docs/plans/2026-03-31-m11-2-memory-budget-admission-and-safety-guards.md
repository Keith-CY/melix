# M11.2 Memory Budget Admission And Safety Guards

## Status

Completed on 2026-04-05 with repository-owned memory-budget load settings, control-plane
headroom-rejection evidence, operator-visible budget summaries, and typed rejection metrics across
the control-plane and native desktop shell.

## Goal

Add virtual-memory budgeting and load-admission guards so large-model streaming remains safe and
operator-visible.

## Scope

- add virtual-memory budget controls
- enforce unsafe-load rejection based on headroom policy
- publish budget and rejection metrics

## Files

- update `packages/protocol/schema/controlplane/v1/`
- update `packages/protocol/descriptors/`
- update `packages/protocol/python/controlplane/v1/`
- update `packages/protocol/swift/controlplane/v1/`
- update `services/control-plane-swift/Sources/`
- update `services/control-plane-swift/Tests/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `apps/macos-menubar/Tests/MenuBarTests/`
- update `task_plan.md`

## Implementation Notes

- Memory-budget policy stays control-plane-owned: operators configure a per-model byte budget once
  and both explicit loads and lazy on-demand loads forward the same effective setting to the
  worker.
- Rejections remain explicit and diagnosable by projecting `budget_bytes`, `headroom_bytes`, and
  `required_bytes` into residency summaries, model info detail, and metrics instead of collapsing
  them into opaque `load_failed` states.
- Existing worker enforcement is preserved; this slice adds admission visibility, typed policy
  propagation, and operator feedback rather than replacing lower-level process-memory checks.

## Verification

- `make proto`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'ControlPlaneServiceTests|ModelCatalogTests|OnDemandModelLoaderTests'`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --scratch-path /tmp/m11_2_cp_cov --enable-code-coverage --filter 'ControlPlaneServiceTests|ModelCatalogTests|OnDemandModelLoaderTests'`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --scratch-path /tmp/m11_2_menu_cov --enable-code-coverage --filter 'ControlPlaneXPCClientTests|DesktopFoundationViewTests|RuntimeViewModelTests'`
- `python3 scripts/swift_changed_line_coverage.py --binary /tmp/m11_2_cp_cov/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata /tmp/m11_2_cp_cov/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift services/control-plane-swift/Sources/WorkerClient/OnDemandModelLoader.swift services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift services/control-plane-swift/Tests/ControlPlaneTests/ModelCatalogTests.swift services/control-plane-swift/Tests/WorkerClientTests/OnDemandModelLoaderTests.swift`
- `python3 scripts/swift_changed_line_coverage.py --binary /tmp/m11_2_menu_cov/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata /tmp/m11_2_menu_cov/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Tests/MenuBarTests/ControlPlaneXPCClientTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift`
- `make py-test`
- `make swift-test`
- `make integration-test`
- `git diff --check`

## Acceptance

- Virtual-memory budgets block unsafe loads before instability.
- Budget controls and rejection paths are measurable and test-covered.
- Native operator settings, model summaries, and load failures expose configured budget plus
  headroom evidence without decoding free-form logs.

## Verification Results

- `make proto`: pass
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'ControlPlaneServiceTests|ModelCatalogTests|OnDemandModelLoaderTests'`: `181 tests in 3 suites passed after 0.081 seconds`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --scratch-path /tmp/m11_2_cp_cov --enable-code-coverage --filter 'ControlPlaneServiceTests|ModelCatalogTests|OnDemandModelLoaderTests'`: `180 tests in 3 suites passed after 0.087 seconds`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --scratch-path /tmp/m11_2_menu_cov --enable-code-coverage --filter 'ControlPlaneXPCClientTests|DesktopFoundationViewTests|RuntimeViewModelTests'`: `202 tests in 3 suites passed after 3.470 seconds`
- `make py-test`: `456 passed in 34.62s`
- `make swift-test`: pass
- `make integration-test`: `60 passed in 754.26s (0:12:34)`
- `git diff --check`: pass

## Metrics Report

- typed memory-budget rejection metrics emitted by the touched control-plane scope:
  - `control_plane.model_load_rejection_count`
  - `control_plane.model_load_last_budget_bytes`
  - `control_plane.model_load_last_headroom_bytes`
  - `control_plane.model_load_last_required_bytes`
  - `control_plane.text_load_memory_budget_rejection_count`
  - `control_plane.text_load_last_budget_bytes`
  - `control_plane.text_load_last_headroom_bytes`
  - `control_plane.text_load_last_required_bytes`
- operator timing metrics exercised by the touched desktop scope:
  - `menu.model_load_ms`
  - `menu.model_settings_ms`
- changed-line coverage for the touched executable scope:
  - Swift control-plane scope: `98.39%` (`305/310`)
  - Swift menu bar scope: `100.00%` (`171/171`)
  - aggregate changed-line coverage across the touched handwritten executable scope:
    `98.96%` (`476/481`)
- protocol schemas, generated protobuf outputs, `packages/protocol/descriptors/melix.pb`, and
  task-planning documents are excluded from executable changed-line coverage because they are
  generated or repository-ownership artifacts rather than handwritten runtime logic.
