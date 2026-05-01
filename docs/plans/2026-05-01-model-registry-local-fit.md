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
3. Reject hard-gated repositories as `blocked` until access is available; Hub `gated="auto"` remains a soft-access signal and does not block download by itself.
4. Estimate artifact bytes from Hub storage or weight/config sibling file sizes, then explicit README/model-card model-size hints as a fallback.
5. Estimate resident bytes from artifact bytes or safetensors parameter count and quantization tags, including FP32/float32/f32 as four bytes per parameter.
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

The Models workspace follows the design-system "Digital Broadsheet" treatment
for the primary Registry surface:

- `DesktopRegistryBroadsheetSection("Model Registry")` owns Hub search inputs and the single primary search action without an outer card fill.
- `DesktopRegistryBroadsheetSection("Unified Model List")` owns the mixed local/download/Hub rows with compact source and suitability badges.
- `DesktopRegistryRowBackground` provides the only list-row fill: a near-invisible neutral wash for inactive rows and the standard accent wash for the selected row.
- `DesktopRegistryInspectorPane("Model Card")` renders Hub or local details as an inspector with a subtle leading separator, not a nested card.
- Registry Roots and Model Settings use the same broadsheet section treatment so the first viewport does not regress into a stack of large gray cards.
- The Tools workspace opens Models Library directly; it is not nested under an additional disclosure group.

Real app screenshots for this state live under
`artifacts/model-registry-local-fit/2026-05-01/`:

- `model-registry-real-app.png`
- `model-registry-real-app-window.png`

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
- `SWIFTPM_DISABLE_SANDBOX=1 swift test --package-path apps/macos-menubar --filter 'DesktopFoundationViewTests/(modelsRegistryUsesDesignSystemWorkspacePrimitives|modelsTabRendersHuggingFaceHubIngressState|modelsTabRendersHubModelCardRunSuitabilityEvidence|modelRegistryRendersEmptyStateAndPlaceholderCard|modelRegistryCoversCacheMissingManagedBlockedUnknownAndGatedBranches|modelsTabRendersModelActionsAndSettings)'`
- `SWIFTPM_DISABLE_SANDBOX=1 swift test --package-path apps/macos-menubar --filter 'DesktopFoundationViewTests/(modelsRegistryUsesDesignSystemWorkspacePrimitives|modelsTabRendersHuggingFaceHubIngressState|modelsTabRendersHubModelCardRunSuitabilityEvidence|modelRegistryRendersEmptyStateAndPlaceholderCard|modelRegistryCoversCacheMissingManagedBlockedUnknownAndGatedBranches|modelsTabRendersModelActionsAndSettings|modelsTabRendersRegistryRootManagement)'`
- `SWIFTPM_DISABLE_SANDBOX=1 swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`
- `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`
- `SWIFTPM_DISABLE_SANDBOX=1 swift test --package-path apps/macos-menubar --filter TempLoRAScreenshotTests/renderCurrentModelRegistryScreenshots` (temporary local screenshot-rendering test; removed before commit)
- `swift test --package-path apps/macos-menubar --filter DesktopFoundationViewTests/modelsTabRendersHuggingFaceHubIngressState`
- `swift test --package-path apps/macos-menubar --filter DesktopFoundationViewTests/modelsTabRendersHubModelCardRunSuitabilityEvidence`
- `swift package --package-path services/control-plane-swift clean`
- `swift test --package-path services/control-plane-swift --filter ControlPlaneServiceTests/executeHandlesOpsSearchHubModelsThroughTheModelOperationsWorker`
- `swift test --package-path services/control-plane-swift --filter ControlPlaneServiceTests/executeHandlesOpsGetHubModelCardThroughTheModelOperationsWorker`

Full Swift verification:

- `make swift-test` did not complete successfully. It passed the protocol package and many control-plane/menu-bar suites, then failed in an existing launch bootstrap test: `AppMainBootstrapTests/launchLive uses the shared launcher path` with `expected launchLive handshake to complete`.
- A subsequent isolated rerun of that test hit a package build-cache compiler mismatch in `apps/macos-menubar/.build` (`module compiled with Swift 6.3.1 cannot be imported by the Swift 6.2.3 compiler`), so the isolated rerun did not reach the test body.

Coverage: changed-line coverage for the touched menu-bar UI files is 100.00%
overall:

- `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift`: 100.00% (70/70)
- `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`: 100.00% (0/0 changed executable lines)
- `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`: 100.00% (11/11)
- Total: 100.00% (81/81)

Review-request follow-up on 2026-05-01:

- Hub sibling-size estimation now ignores sibling records that omit `rfilename` or are not weight/config artifacts.
- FP32 parameter metadata is estimated at four bytes per parameter.
- `gated="auto"` is treated as a soft Hub access state rather than a hard local-fit block.
- README/model-card size fallback only accepts explicit model-size hints, avoiding batch/context/vocab-size matches.
- Registry count/byte probes use generic metric values instead of timing-only `valueMs`.
- `RuntimeViewModel` caches unified registry entries and refreshes them when local models, managed downloads, or Hub results change.
- Hub search/card download gating now shares one local-fit protocol implementation.
- Local/managed registry cards no longer render state text as a recommended action.
- Run-suitability evidence reports when additional reasons are hidden instead of silently truncating.
- CLI human output now uses `local_fit_status` and formats resident bytes with binary units while JSON remains numeric.
- The Hugging Face publish backend shares the same deterministic published-file collector as upload receipts, restoring the maintenance-service test path.

Review follow-up verification:

- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_hub_catalog.py -q`: 20 passed.
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_maintenance_service.py -q`: 157 passed.
- `SWIFTPM_DISABLE_SANDBOX=1 swift test --filter 'MelixCLIRunnerTests'`: 145 tests passed.
- `SWIFTPM_DISABLE_SANDBOX=1 swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`: 368 tests passed.
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" COVERAGE_FILE=/tmp/model-registry-review-python.coverage uv run --project services/mlx-worker-python coverage run --source=services/mlx-worker-python/worker,services/mlx-worker-python/tests -m pytest services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_maintenance_service.py -q && PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" COVERAGE_FILE=/tmp/model-registry-review-python.coverage uv run --project services/mlx-worker-python coverage json -o /tmp/model-registry-review-python-coverage.json && python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/model-registry-review-python-coverage.json services/mlx-worker-python/worker/model_ops/hub_catalog.py services/mlx-worker-python/worker/engine/maintenance_core.py services/mlx-worker-python/worker/model_ops/upload_receipt_pipeline.py services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_maintenance_service.py`: 98.78% changed-line coverage (81/82).
- `SWIFTPM_DISABLE_SANDBOX=1 swift test --enable-code-coverage --filter 'MelixCLIRunnerTests' && python3 scripts/swift_changed_line_coverage.py --binary .build/arm64-apple-macosx/debug/melixPackageTests.xctest/Contents/MacOS/melixPackageTests --profdata .build/arm64-apple-macosx/debug/codecov/default.profdata Sources/MelixCLICore/MelixCLI.swift tests/MelixCLITests/MelixCLIRunnerTests.swift`: 95.45% changed-line coverage (21/22).
- `SWIFTPM_DISABLE_SANDBOX=1 swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'RuntimeViewModelTests|DesktopFoundationViewTests' && python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`: 100.00% changed-line coverage (89/89).

Second review and CI follow-up on 2026-05-02:

- The current branch was fast-forward checked against its remote and then merged with `origin/main` so the PR head contains the `pr-scoped-performance` workflow support scripts used by the base workflow.
- `RuntimeHubModelSearchResultState` now carries raw artifact and resident byte values alongside display strings, and `sizeText` uses the raw values for zero detection instead of comparing formatted `"0 B"` strings.
- `_estimated_resident_bytes` now uses one `base_size -> ceil(base_size * RESIDENT_MEMORY_OVERHEAD_FACTOR)` path for artifact-size and parameter-count estimates.
- The merged CLI metric-literal path now normalizes exponent notation to lowercase `e`, keeping JSON metric patching deterministic across Swift/Foundation formatter behavior.

Second follow-up verification:

- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_hub_catalog.py -q`: 20 passed.
- `SWIFTPM_DISABLE_SANDBOX=1 swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests/hubSearchResultSizeTextUsesRawByteValues|RuntimeViewModelTests/modelRegistryEntriesMergeLocalManagedDownloadAndHubFitState'`: 2 tests passed.
- `python3 scripts/pr_scoped_performance_scope.py --registry infra/perf/pr_scoped_probes.json --changed-files-json /private/tmp/melix-pr133-changed-files.json --output /private/tmp/melix-pr133-scope/scope.json`: selected 2 scoped performance probes for the PR diff.
- `python3 scripts/pr_scoped_performance_report.py --scope /private/tmp/melix-pr133-scope/scope.json --results-dir /private/tmp/melix-pr133-probes --output-dir /private/tmp/melix-pr133-report --format terminal`: completed report rendering; local smoke intentionally had no probe artifacts, so the report status was `verification_failed` with missing results rather than a script crash.
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_maintenance_service.py::test_run_bench_persists_report_without_reading_report_file services/mlx-worker-python/tests/test_maintenance_service.py::test_run_bench_measures_runtime_behavior_from_loaded_backend services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_bench_report_probe`: 3 passed.
- `SWIFTPM_DISABLE_SANDBOX=1 swift test --filter MelixCLIRunnerTests`: 145 tests passed.
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" COVERAGE_FILE=/private/tmp/model-registry-ci-followup-python.coverage uv run --project services/mlx-worker-python coverage run --source=services/mlx-worker-python/worker,services/mlx-worker-python/tests -m pytest services/mlx-worker-python/tests/test_hub_catalog.py -q`; `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" COVERAGE_FILE=/private/tmp/model-registry-ci-followup-python.coverage uv run --project services/mlx-worker-python coverage json -o /private/tmp/model-registry-ci-followup-python-coverage.json`; `python3 scripts/python_changed_line_coverage.py --coverage-json /private/tmp/model-registry-ci-followup-python-coverage.json services/mlx-worker-python/worker/model_ops/hub_catalog.py`: 100.00% changed-line coverage (4/4).
- `SWIFTPM_DISABLE_SANDBOX=1 swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'RuntimeViewModelTests/hubSearchResultSizeTextUsesRawByteValues|RuntimeViewModelTests/modelRegistryEntriesMergeLocalManagedDownloadAndHubFitState'`; `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`: 100.00% changed-line coverage (53/53).
- `SWIFTPM_DISABLE_SANDBOX=1 swift test --enable-code-coverage --filter MelixCLIRunnerTests`; `python3 scripts/swift_changed_line_coverage.py --binary .build/arm64-apple-macosx/debug/melixPackageTests.xctest/Contents/MacOS/melixPackageTests --profdata .build/arm64-apple-macosx/debug/codecov/default.profdata Sources/MelixCLICore/MelixCLIJSON.swift`: 100.00% changed-line coverage (1/1).
