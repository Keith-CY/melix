# Batch Decode Token Eval Counter Plan

## Context

Issue #1642 tracks the Gemma E4B release serving gap. The latest three-way
release artifact under
`.runtime/serving-comparison/gemma-e4b-20260601-latest-ae720be-rerun9/threeway/gemma-e4b-mainae720be-release-threeway-20260601-rerun9-full`
still fails the 25 percent acceptance recompute for 128/c1, 128/c2, and
1024/c1. The existing Melix metrics show
`swift_text.decode_batch_token_id_total_us` dominates
`swift_text.decode_batch_loop_total_us`, but that bucket currently includes the
MLX lazy graph synchronization needed to make the argmax token IDs available on
the host.

## Goal

Close the #1659 attribution gap for homogeneous batch decode by splitting token
graph synchronization time from host token-id extraction time.

## Scope

- Add batch decode token-eval counters alongside the existing token-id counters.
- Preserve generation semantics, request ordering, stop-token handling,
  cancellation behavior, and streamed output cadence.
- Keep the existing `decode_batch_token_id_*` counters present so current
  dashboards and reports remain compatible. In the batched greedy path, narrow
  those counters to host token-id extraction after MLX synchronization.

## Implementation Steps

1. Extend `DecodeBatchProbeSummary` with
   `decodeTokenEvalTotalMicros`, `decodeTokenEvalCallCount`, and an average
   helper.
2. Add zero defaults and metric recording for:
   - `swift_text.decode_batch_token_eval_total_us`
   - `swift_text.decode_batch_token_eval_call_count`
   - `swift_text.decode_batch_token_eval_avg_us`
3. In the homogeneous greedy batch path, time the `asArray` materialization as
   token-eval time and time the post-materialization `UInt32` to `Int`
   extraction as token-id time.
4. In the non-batched sample path, keep token-eval equal to the existing token-id
   materialization point so the probe remains comparable.
5. Update focused Swift tests to assert the new metrics exist and are populated
   for batch decode.

## Performance Probes And Success Metrics

- Focused Swift tests prove the new counters flow from runtime summaries into
  `MetricsStore`.
- The registered same-cohort batching probe should continue to pass and report
  existing batch-size evidence. Its deterministic worker payload remains a
  batch-shape probe, not a token-loop microtiming source.
- A future real Gemma E4B rerun should inspect whether
  `decode_batch_token_eval_total_us` rather than `decode_batch_token_id_total_us`
  dominates the decode loop before implementing #1660 cadence optimizations.
- Dashboard readers should compare the two average counters with their call-count
  grain in mind: `decode_batch_token_eval_avg_us` is averaged over one MLX
  materialization call per batch step, while `decode_batch_token_id_avg_us` is
  averaged over the per-request host `UInt32` to `Int` extraction calls inside
  each batch step. Average batch size is therefore required before comparing the
  two averages directly.

## Verification

```bash
swift test --package-path services/mlx-text-worker-swift --enable-code-coverage --filter 'WorkerScaffoldTests/testMetricsStoreTracksCountersAndTimings|WorkerScaffoldTests/testDecodeStreamingRpcBatchesHomogeneousDeterministicDecodeRequests|WorkerScaffoldTests/testAutoSwiftMLXBackendBatchDecodeUsesProcessorPathForRepetitionPenalty|WorkerScaffoldTests/testAutoSwiftMLXBackendReusesBatchCacheAcrossHomogeneousDecodeSteps|WorkerScaffoldTests/testAutoSwiftMLXBackendBatchDecodeRebuildsCacheWhenOneOfThreePeersAborts'

uv run --project services/mlx-worker-python --extra mlx python scripts/swift_changed_line_coverage.py --binary services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/MelixTextWorkerSwiftPackageTests.xctest/Contents/MacOS/MelixTextWorkerSwiftPackageTests --profdata services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata --diff-from origin/main services/mlx-text-worker-swift/Sources/Core/Runtime/SwiftMLXBackend.swift services/mlx-text-worker-swift/Sources/Core/Runtime/TextRuntime.swift services/mlx-text-worker-swift/Sources/Core/Inference/TextDecodeEngine.swift services/mlx-text-worker-swift/Sources/Core/MetricsStore.swift services/mlx-text-worker-swift/Sources/Core/Runtime/DeterministicTextBackend.swift services/mlx-text-worker-swift/Tests/CoreTests/WorkerScaffoldTests.swift

PYTHONPATH=$PWD:$PWD/scripts COVERAGE_FILE=.coverage.three_way uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest tests/test_three_way_serving_compare.py -q

PYTHONPATH=$PWD:$PWD/scripts COVERAGE_FILE=.coverage.three_way uv run --project services/mlx-worker-python --extra mlx coverage json -o coverage-three-way.json

python3 scripts/changed_scope_coverage.py --coverage-json coverage-three-way.json scripts/three_way_serving_compare.py tests/test_three_way_serving_compare.py

python3 scripts/same_cohort_batching_probe.py --metrics

git diff --check
```

## Metrics Report

- Swift focused coverage run: 5 selected WorkerScaffold tests passed with 0
  failures and 0 skips.
- Swift changed-line coverage: 100.00 percent, 40/40 covered.
- Python focused test run: `tests/test_three_way_serving_compare.py` passed,
  44/44 tests.
- Python changed-scope coverage: 100 percent, 3/3 measurable changed lines
  covered.
- Same-cohort batching probe: exit 0, `failure_count=0`, `status_warning=1`,
  `scheduler_admission_cohort_size=2`, and `worker_model_eval_batch_size=1`.
  The warning is the expected deterministic control-plane probe shape and does
  not represent the new Swift MLX token-eval counters.
- #1642 acceptance status remains unresolved until a fresh Gemma E4B three-way
  rerun shows the 25 percent threshold recompute passing.
