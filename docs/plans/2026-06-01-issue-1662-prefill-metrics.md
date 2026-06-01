# Issue 1662 Prefill Metrics Reconciliation Plan

## Context

Issue #1662 is an open child of the #1642 Gemma E4B serving performance root.
Recent release evidence showed `scheduler.prefill_chunk_target_tokens=16` while
the Swift text worker reported `swift_text.prefill_chunk_target_tokens=512`.
Those values are both expected today, but the metric names do not explain their
different semantics.

The scheduler value is the boundary-safe progress chunk used for request
admission and streamed progress accounting. The worker value is the prefill step
requested from the runtime, and the actual model-call window can diverge again
when acceleration policies widen or reshape the prefill window.

## Goal

Expose explicit Swift text worker metrics that identify the requested worker
prefill step and the effective model prefill window used by the runtime call, so
benchmark artifacts can distinguish scheduler progress boundaries from worker
runtime windows.

## Scope

- Preserve the existing `swift_text.prefill_chunk_target_tokens` metric for
  compatibility.
- Add explicit worker prefill metrics for the requested step and the effective
  model window.
- Thread the effective window from the runtime backend through the worker
  prefill result.
- Cover both text-only and vision-bearing prompt paths in focused Swift worker
  tests.
- Document the new metric semantics in this plan.

Out of scope:

- Changing scheduler prefill progress chunk selection.
- Changing worker prefill batching or runtime window policy.
- Regenerating protobuf schemas.
- Running the full Gemma E4B release comparison; this slice only closes the
  metric attribution gap needed by that comparison.

## Metric Keys

- `swift_text.worker_prefill_requested_step_tokens`: the prefill step size the
  worker received in the prefill request and passed toward the runtime.
- `swift_text.worker_prefill_effective_window_tokens`: the runtime window size
  used for the model prepare/prefill call after applying worker-side
  acceleration policy.
- `swift_text.prefill_chunk_target_tokens`: existing compatibility metric. It
  remains the worker request step size and should not be compared directly with
  `scheduler.prefill_chunk_target_tokens` without the two worker-prefill metrics
  above.

## Implementation Steps

1. Add red worker tests.
   - Text-only prompt with a 512-token worker prefill step records requested and
     effective worker window metrics as 512 while the compatibility chunk metric
     remains 512.
   - Vision-bearing prompt with a 16-token worker prefill step records requested
     and effective worker window metrics as 16.
2. Extend runtime prefill results.
   - Add requested-step and effective-window fields to `RuntimePrefillResult`.
   - Populate them from the deterministic backend, Swift MLX backend, and test
     fake backend.
3. Surface the metrics in `TextPrefillEngine`.
   - Record the explicit worker prefill metrics after successful prefill.
   - Keep the existing compatibility metric unchanged.
4. Update metric defaults and verify changed-line coverage.

## Performance Probes And Success Metrics

- Metrics are written once per successful prefill request, not from the runtime
  token loop.
- The deterministic focused tests should pass with code coverage enabled.
- Changed-line coverage for the touched Swift worker files must be at least
  95 percent before commit.
- A follow-up Gemma E4B serving report can use the new metric pair to explain a
  scheduler progress target of 16 alongside a worker model window of 512.

## Verification

```bash
swift test --package-path services/mlx-text-worker-swift --enable-code-coverage --filter 'WorkerScaffoldTests/testPrefillMetricsSeparateTextWorkerWindowFromChunkCompatibility|WorkerScaffoldTests/testPrefillMetricsRecordVisionWorkerWindow'

uv run --project services/mlx-worker-python --extra mlx python scripts/swift_changed_line_coverage.py --binary services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/MelixTextWorkerSwiftPackageTests.xctest/Contents/MacOS/MelixTextWorkerSwiftPackageTests --profdata services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/mlx-text-worker-swift/Sources/Core/Inference/TextPrefillEngine.swift services/mlx-text-worker-swift/Sources/Core/MetricsStore.swift services/mlx-text-worker-swift/Sources/Core/Runtime/TextRuntime.swift services/mlx-text-worker-swift/Sources/Core/Runtime/DeterministicTextBackend.swift services/mlx-text-worker-swift/Sources/Core/Runtime/SwiftMLXBackend.swift services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift services/mlx-text-worker-swift/Tests/CoreTests/WorkerScaffoldTests.swift

git diff --check
```

The final PR gate must also follow the repository default commands and
pre-commit performance report rules before claiming PR readiness.

## Metrics Report

Verification was run on June 1, 2026 from the
`codex/issue-1662-prefill-metrics-20260601` worktree.

- Initial red run:
  - `swift test --package-path services/mlx-text-worker-swift --enable-code-coverage --filter 'WorkerScaffoldTests/testPrefillMetricsSeparateTextWorkerWindowFromChunkCompatibility|WorkerScaffoldTests/testPrefillMetricsRecordVisionWorkerWindow'`
  - Result: failed because `swift_text.worker_prefill_requested_step_tokens`
    and `swift_text.worker_prefill_effective_window_tokens` were not recorded.
- Focused final run:
  - `swift test --package-path services/mlx-text-worker-swift --enable-code-coverage --filter 'WorkerScaffoldTests/testMetricsStoreTracksCountersAndTimings|WorkerScaffoldTests/testAutoSwiftMLXBackendPrefillUsesLiveModelContainerBridge|WorkerScaffoldTests/testAutoSwiftMLXBackendPrefillAppliesAcceleratedPrefillPolicyForLiveBridge|WorkerScaffoldTests/testTextRuntimeForwardsPrefillAndDefaultPrefillThrowsUnavailable|WorkerScaffoldTests/testPrefillCanRestoreBoundarySnapshotsFromCacheHints|WorkerScaffoldTests/testPrefillRestoreWalksBackPartialPrefixesToSafeBoundary|WorkerScaffoldTests/testPrefillRecordsBoundarySafeChunkMetricsForLongPrompts|WorkerScaffoldTests/testPrefillMetricsSeparateTextWorkerWindowFromChunkCompatibility|WorkerScaffoldTests/testPrefillMetricsRecordVisionWorkerWindow'`
  - Result: passed, 9 tests, 0 failures.
- Changed-line coverage:
  - `uv run --project services/mlx-worker-python --extra mlx python scripts/swift_changed_line_coverage.py --binary services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/MelixTextWorkerSwiftPackageTests.xctest/Contents/MacOS/MelixTextWorkerSwiftPackageTests --profdata services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/mlx-text-worker-swift/Sources/Core/Inference/TextPrefillEngine.swift services/mlx-text-worker-swift/Sources/Core/MetricsStore.swift services/mlx-text-worker-swift/Sources/Core/Runtime/TextRuntime.swift services/mlx-text-worker-swift/Sources/Core/Runtime/DeterministicTextBackend.swift services/mlx-text-worker-swift/Sources/Core/Runtime/SwiftMLXBackend.swift services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift services/mlx-text-worker-swift/Tests/CoreTests/WorkerScaffoldTests.swift`
  - Result: `TOTAL 100.00% 128/128`.
- Runtime metrics:
  - New metrics are written once per successful prefill request in
    `TextPrefillEngine`.
  - The change is observational and does not alter scheduler chunk selection,
    worker prefill batching, or runtime window policy.
