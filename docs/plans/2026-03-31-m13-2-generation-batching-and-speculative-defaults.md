# M13.2 Generation, Batching, And Speculative Defaults

## Goal

Expose the generation, batching, and speculative-decoding defaults that shape serving behavior for the local gateway.

## Scope

- add default token and sampling controls
- expose batching and stream-interval settings
- add draft-model and `num-draft-tokens` configuration
- keep timeout-default and rate-limit-adjacent serving behavior inspectable where it shapes request admission

## Implementation Slices

### Slice 1

Status: completed on 2026-04-05

- add a typed serving-defaults state model for gateway-level generation defaults
- persist operator defaults for `temperature`, `top_p`, `max_tokens`, and `stream_interval_tokens`
- project requested and effective generation defaults through `ServerSnapshot`
- route chat and completions request shaping through gateway defaults before request-level overrides
- migrate the existing Window UI advanced-default controls off desktop-only draft state

### Slice 2

Status: completed on 2026-04-06

- add batching and admission defaults including concurrent-processing and batch-size fields
- keep admission-shaping defaults visible beside timeout and rate-limit state
- surface effective batching defaults through the same snapshot path as generation defaults

### Slice 3

- add speculative-decoding defaults including draft-model selection and `num_draft_tokens`
- fail explicitly when speculative defaults target unsupported served models
- keep speculative effective state inspectable after model-level merges

## Files

- update `services/control-plane-swift/Sources/Requests/`
- update `services/control-plane-swift/Sources/HTTPGateway/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `apps/macos-menubar/Sources/AppMain/`

## Implementation Notes

- Defaults should remain separate from per-request overrides.
- Speculative settings must align with capability support and fail explicitly when unsupported.
- Effective values should remain visible after model-level merges.
- Serving defaults that influence admission or cancellation should stay visible beside sampling defaults, not buried in transport-only state.

## Key Probes

- `gateway.serving_defaults_apply_ms`
- `gateway.serving_defaults_persist_failures`
- `gateway.generation_default_merge_count`
- `gateway.speculative_config_apply_ms`

## Verification

- focused Swift tests for control-plane, HTTP gateway, and Window UI surfaces touched by the slice
- changed-line coverage for touched Swift files must be `>=95%`
- `make swift-test`
- `make integration-test`
- `git diff --check`

## Acceptance

- Generation, batching, and speculative defaults are operator-visible and test-covered.
- Effective defaults are consistent across the gateway and desktop shell.
- Adjacent serving defaults that shape request admission remain inspectable after settings merges.

## Slice 2 Verification

- `make proto`: pass
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --skip-build --filter 'GatewayServingDefaultsStoreTests'`: `4 tests in 1 suite passed`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --skip-build --filter 'TextEndpointContractTests'`: `36 tests in 1 suite passed`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --skip-build --filter 'OpenAIHandlerTests'`: `101 tests in 1 suite passed`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --skip-build --filter 'ControlPlaneServiceTests'`: `157 tests in 1 suite passed`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --skip-build --filter 'HTTPGatewayTests.RequestCoordinatorTests/gatewayBatchingDefaultsCanExpandContinuousBatchCapacity()'`: `1 test in 1 suite passed`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --skip-build --filter 'HTTPGatewayTests.RequestCoordinatorTests/gatewayBatchingDefaultsCanDisableContinuousBatchAdmissions()'`: `1 test in 1 suite passed`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'RuntimeViewModelTests|ControlPlaneXPCClientTests|DesktopShellStateTests|DesktopFoundationViewTests'`: `246 tests in 4 suites passed after 4.357 seconds`
- `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata /tmp/m13_2_cp_profdata_pieces/merged.profdata services/control-plane-swift/Sources/HTTPGateway/OpenAI/GatewayServingDefaultsStore.swift services/control-plane-swift/Sources/Requests/ChatRequestTranslator.swift services/control-plane-swift/Sources/Requests/RequestCoordinator.swift services/control-plane-swift/Sources/Requests/TextRequestShaper.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift services/control-plane-swift/Tests/ControlPlaneTests/GatewayServingDefaultsStoreTests.swift services/control-plane-swift/Tests/ControlPlaneTests/TextEndpointContractTests.swift services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift services/control-plane-swift/Tests/HTTPGatewayTests/RequestCoordinatorTests.swift`: `95.41%` (`457/479`)
- `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Sources/AppMain/Models/DesktopShellState.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Tests/MenuBarTests/ControlPlaneXPCClientTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopShellStateTests.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift`: `99.59%` (`240/241`)
- aggregate changed-line coverage across the touched handwritten executable scope: `96.81%` (`697/720`)
- `make integration-test`: `66 passed in 883.49s (0:14:43)`
- `make swift-test`: failed outside the touched scope when `services/mlx-text-worker-swift` exited with unexpected signal `11` during `WorkerScaffoldTests`
- `git diff --check`: pass
