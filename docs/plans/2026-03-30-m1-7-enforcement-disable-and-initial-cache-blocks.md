# M1.7 Enforcement Disable And Initial Cache Blocks

## Goal

Allow memory enforcement to be fully disabled when explicitly configured and make initial cache-block sizing a first-class runtime control.

## Scope

- add an explicit full-disable memory-enforcement mode in the Swift text worker
- add configurable initial cache-block targeting for prefill block-table creation
- expose both controls through startup metrics and runtime behavior

## Files

- update `services/mlx-text-worker-swift/Sources/Core/HotCacheStore.swift`
- update `services/mlx-text-worker-swift/Sources/Core/MetricsStore.swift`
- update `services/mlx-text-worker-swift/Sources/Core/WorkerConfiguration.swift`
- update `services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift`
- update `services/mlx-text-worker-swift/Sources/Core/WorkerServices.swift`
- update `services/mlx-text-worker-swift/Tests/CoreTests/WorkerScaffoldTests.swift`

## Implementation Notes

- use explicit environment variables:
  - `MELIX_SWIFT_TEXT_WORKER_DISABLE_MEMORY_ENFORCEMENT`
  - `MELIX_SWIFT_TEXT_WORKER_INITIAL_CACHE_BLOCKS`
- disabling enforcement should bypass model-load and prefill memory-budget checks without disabling context-limit validation
- initial cache-block targeting should shape persisted block tables so the choice survives cache save and restore paths
- publish startup metrics for:
  - `swift_text.memory_enforcement_disabled`
  - `swift_text.cache_initial_block_target`

## Verification

- `swift test --package-path services/mlx-text-worker-swift --filter WorkerScaffoldTests`
- `swift test --package-path services/mlx-text-worker-swift --enable-code-coverage --filter WorkerScaffoldTests`
- `python3 scripts/swift_changed_line_coverage.py --binary services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/MelixTextWorkerSwiftPackageTests.xctest/Contents/MacOS/MelixTextWorkerSwiftPackageTests --profdata services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/mlx-text-worker-swift/Sources/Core/HotCacheStore.swift services/mlx-text-worker-swift/Sources/Core/MetricsStore.swift services/mlx-text-worker-swift/Sources/Core/WorkerConfiguration.swift services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift services/mlx-text-worker-swift/Sources/Core/WorkerServices.swift`
- `git diff --check`

## Acceptance

- operators can explicitly disable memory enforcement and see that state reflected in startup metrics
- disabled enforcement allows oversized load and prefill requests to proceed while preserving context-limit checks
- initial cache-block targeting changes block-table sizing and is visible through metrics and cache stats
