# Model Registry Local Fit Plan

## Summary

Melix Model Registry now treats local models, managed downloads, and Hugging Face discovery results as one operator-facing registry list. Hub metadata is still fetched on demand through search and model-card inspection; opening the Registry does not initiate network requests.

This slice adds a local run suitability classifier for Hub models:

- `good`: MLX-compatible metadata and estimated resident size within the local memory comfort budget.
- `heavy`: MLX-compatible metadata but estimated resident size exceeds the comfort budget; download remains available.
- `blocked`: unsupported for the local Melix runtime, for example non-MLX metadata, unsupported pipeline, or gated access.
- `unknown`: metadata is insufficient to estimate local fit.

The default local target comes from the runtime device probe. It records chip class and memory for suitability math, but does not store or display serial numbers or other sensitive hardware identifiers.

## Hub Metadata Contract

The worker requests Hugging Face model metadata only during search and model-card inspection. The implementation uses the Hub model API fields exposed by `full`, `cardData`, and `config`/expanded metadata, including tags, library name, pipeline tag, gated state, sibling file sizes, storage size, and safetensors parameter metadata.

Reference: [Hugging Face HfApi list_models documentation](https://huggingface.co/docs/huggingface_hub/main/package_reference/hf_api).

## Local Fit Rules

The worker evaluates each `HubModelSummary` and `HubModelCard` with the same rule set:

1. Reject non-MLX models as `blocked`.
2. Reject Melix-unsupported pipeline tags as `blocked`.
3. Reject gated repositories as `blocked` until access is available.
4. Estimate artifact bytes from Hub storage or sibling file sizes, then README/model-card size hints as a fallback.
5. Estimate resident bytes from artifact bytes or safetensors parameter count and quantization tags.
6. Return `unknown` when size metadata is missing.
7. Return `heavy` when estimated resident bytes exceed 60% of probed local memory.
8. Return `good` when metadata is MLX-compatible and estimated resident bytes fit the comfort budget.

## Protocol Fields

`HubModelSummary` and `HubModelCard` now include:

- `local_fit_status`
- `local_fit_reasons`
- `estimated_artifact_bytes`
- `estimated_resident_bytes`
- `parameter_count`
- `quantization_summary`
- `gated`
- `recommended_action`

The fields are added to both worker and control-plane protobuf schemas and generated Swift/Python outputs.

## UI Behavior

The macOS menu bar Models surface exposes a unified Model Registry list:

- Local rows show source `Local`, state, memory, and installed suitability.
- Managed download rows show source `Managed Download`, queue state, and progress.
- Hub rows show source `Hugging Face`, task, recommendation, run suitability, and size evidence.

Model Card details include a Run Suitability evidence block with artifact size, resident size, parameter count, quantization summary, and local-fit reasons.

Download is disabled for `blocked` Hub rows. `heavy` rows remain downloadable and display the risk classification.

The Models workspace uses the shared Melix desktop primitives rather than
native SwiftUI structural containers for the primary Registry surface:

- `MelixSectionCard("Model Registry")` owns Hub search inputs and the single primary search action.
- `MelixSectionCard("Unified Model List")` owns the mixed local/download/Hub rows with compact source and suitability badges.
- `MelixSectionCard("Model Card")` owns local summary details or Hub card metadata, including Run Suitability evidence.
- The Tools workspace opens Models Library directly; it is not nested under an additional disclosure group.

## Probes

This slice records:

- `hub.metadata_enrichment_latency_ms`
- `hub.local_fit_estimated_resident_bytes`
- `registry.unified_entry_count`
- `registry.blocked_download_attempt_count`

## Verification

Completed so far:

- `make proto`
- `make py-test`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_maintenance_service.py -q`
- `swift test --package-path apps/macos-menubar --filter RuntimeViewModelTests/modelRegistryEntriesMergeLocalManagedDownloadAndHubFitState`
- `swift test --package-path apps/macos-menubar --filter RuntimeViewModelTests/blockedHubDownloadIsPreventedWhileHeavyRemainsAllowed`
- `SWIFTPM_DISABLE_SANDBOX=1 swift test --package-path apps/macos-menubar --filter DesktopFoundationViewTests/modelsRegistryUsesDesignSystemWorkspacePrimitives`
- `SWIFTPM_DISABLE_SANDBOX=1 swift test --package-path apps/macos-menubar --filter 'DesktopFoundationViewTests/(modelsTabRendersModelActionsAndSettings|modelsRegistryUsesDesignSystemWorkspacePrimitives|modelsTabRendersHuggingFaceHubIngressState|modelsTabRendersHubModelCardRunSuitabilityEvidence|modelsTabRendersRegistryRootManagement|modelsTabButtonsDispatchActions)'`
- `SWIFTPM_DISABLE_SANDBOX=1 swift test --package-path apps/macos-menubar --filter 'DesktopFoundationViewTests/(modelsRegistryUsesDesignSystemWorkspacePrimitives|modelsTabRendersHuggingFaceHubIngressState|modelsTabRendersHubModelCardRunSuitabilityEvidence)'`
- `SWIFTPM_DISABLE_SANDBOX=1 swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`
- `SWIFTPM_DISABLE_SANDBOX=1 swift test --package-path apps/macos-menubar --filter 'DesktopFoundationViewTests/(modelRegistryRendersEmptyStateAndPlaceholderCard|modelRegistryCoversCacheMissingManagedBlockedUnknownAndGatedBranches)'`
- `SWIFTPM_DISABLE_SANDBOX=1 swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`
- `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`
- `SWIFTPM_DISABLE_SANDBOX=1 swift test --package-path apps/macos-menubar --filter TempLoRAScreenshotTests/renderCurrentModelRegistryScreenshot` (temporary local screenshot-rendering test; removed before commit)
- `swift test --package-path apps/macos-menubar --filter DesktopFoundationViewTests/modelsTabRendersHuggingFaceHubIngressState`
- `swift test --package-path apps/macos-menubar --filter DesktopFoundationViewTests/modelsTabRendersHubModelCardRunSuitabilityEvidence`
- `swift package --package-path services/control-plane-swift clean`
- `swift test --package-path services/control-plane-swift --filter ControlPlaneServiceTests/executeHandlesOpsSearchHubModelsThroughTheModelOperationsWorker`
- `swift test --package-path services/control-plane-swift --filter ControlPlaneServiceTests/executeHandlesOpsGetHubModelCardThroughTheModelOperationsWorker`

Full Swift verification:

- `make swift-test` did not complete successfully. It passed the protocol package and many control-plane/menu-bar suites, then failed in an existing launch bootstrap test: `AppMainBootstrapTests/launchLive uses the shared launcher path` with `expected launchLive handshake to complete`.
- A subsequent isolated rerun of that test hit a package build-cache compiler mismatch in `apps/macos-menubar/.build` (`module compiled with Swift 6.3.1 cannot be imported by the Swift 6.2.3 compiler`), so the isolated rerun did not reach the test body.

Coverage: changed-line coverage for the touched menu-bar UI files is 98.24%
overall:

- `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift`: 97.78% (441/451)
- `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`: 100.00% (1/1)
- `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`: 99.43% (173/174)
- Total: 98.24% (615/626)
