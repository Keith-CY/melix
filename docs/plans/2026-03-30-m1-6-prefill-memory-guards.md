# M1.6 Prefill Memory Guards

## Goal

Protect Melix from oversized prefill requests and fallback paths that would exceed safe memory limits during request execution.

## Scope

- add inline prefill guards in the Swift text worker before prefill allocation work begins
- protect large-context requests, process-budget overruns, and quadratic fallback paths
- make guard failures observable through explicit status codes and worker metrics

## Files

- update `services/mlx-text-worker-swift/Sources/Core/Inference/TextPrefillEngine.swift`
- update `services/mlx-text-worker-swift/Sources/Core/MetricsStore.swift`
- update `services/mlx-text-worker-swift/Sources/Core/WorkerConfiguration.swift`
- update `services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift`
- update `services/mlx-text-worker-swift/Sources/Core/WorkerServices.swift`
- update `services/mlx-text-worker-swift/Tests/CoreTests/WorkerScaffoldTests.swift`

## Implementation Notes

- guard logic should run before irreversible allocation work begins
- configuration should support:
  - `MELIX_SWIFT_TEXT_WORKER_PROCESS_MEMORY_BUDGET_BYTES`
  - `MELIX_SWIFT_TEXT_WORKER_PREFILL_MEMORY_HEADROOM_BYTES`
  - `MELIX_SWIFT_TEXT_WORKER_PREFILL_QUADRATIC_GUARD_TOKEN_THRESHOLD`
- guard failures should surface explicit worker error codes and structured details
- metrics should record both aggregate guard rejections and the last rejected prompt and budget details

## Verification

- `swift test --package-path services/mlx-text-worker-swift --filter WorkerScaffoldTests`
- `swift test --package-path services/mlx-text-worker-swift --enable-code-coverage --filter WorkerScaffoldTests`
- `python3 scripts/swift_changed_line_coverage.py --binary services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/MelixTextWorkerSwiftPackageTests.xctest/Contents/MacOS/MelixTextWorkerSwiftPackageTests --profdata services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/mlx-text-worker-swift/Sources/Core/WorkerConfiguration.swift services/mlx-text-worker-swift/Sources/Core/MetricsStore.swift services/mlx-text-worker-swift/Sources/Core/Inference/TextPrefillEngine.swift services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift services/mlx-text-worker-swift/Sources/Core/WorkerServices.swift`
- `git diff --check`

## Acceptance

- oversized prefill requests fail with explicit guard errors
- context-limit, projected-memory, and quadratic-fallback guard failures are all test-covered
- worker metrics expose guard rejection counters and the last rejected request budget details
