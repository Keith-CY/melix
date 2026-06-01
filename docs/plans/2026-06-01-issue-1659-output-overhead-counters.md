# Issue 1659 Output Overhead Counter Plan

## Context

Issue #1659 asks for lightweight token-loop breakdown counters across the Swift
text generation path. Prior slices already exposed model eval, token eval,
token-id, sample, detokenize, and worker stream-yield counters for the decode
runtime. The remaining attribution gap for #1642 is the output path around
Harmony filtering, worker gRPC writes, control-plane event handling, and SSE
frame emission.

## Goal

Expose low-overhead output-path counters in the live metrics snapshot and the
Gemma E4B three-way report so #1660 can choose token cadence optimizations from
measured evidence instead of inference.

## Scope

- Add decode/generate worker counters for Harmony filtering and gRPC writes.
- Add control-plane counters for worker event handling and SSE frame emission.
- Surface the new counters in the three-way serving comparison Markdown report.
- Preserve streamed event order, first-token behavior, disconnect handling,
  resume behavior, and existing metric names.
- Do not optimize cadence, batching, or token materialization in this slice.

## Metric Keys

Worker metrics:

- `swift_text.decode_harmony_filter_total_us`
- `swift_text.decode_harmony_filter_call_count`
- `swift_text.decode_harmony_filter_avg_us`
- `swift_text.decode_grpc_write_total_us`
- `swift_text.decode_grpc_write_call_count`
- `swift_text.decode_grpc_write_avg_us`
- `swift_text.generate_harmony_filter_total_us`
- `swift_text.generate_harmony_filter_call_count`
- `swift_text.generate_harmony_filter_avg_us`
- `swift_text.generate_grpc_write_total_us`
- `swift_text.generate_grpc_write_call_count`
- `swift_text.generate_grpc_write_avg_us`

Control-plane metrics:

- `http.worker_event_handle_total_us`
- `http.worker_event_handle_call_count`
- `http.worker_event_handle_avg_us`
- `http.sse_write_total_us`
- `http.sse_write_call_count`
- `http.sse_write_avg_us`

## Implementation Steps

1. Add metric defaults and helper recording methods.
   - Extend the Swift text worker `MetricsStore` default storage with worker
     output counters.
   - Extend the control-plane `MetricsStore` default storage with event-handle
     and SSE counters.
   - Add tiny helpers that record total, count, and average with integer
     microsecond elapsed time.
2. Add red worker tests.
   - Update the existing metrics-store test to assert the new worker keys start
     at zero.
   - Extend deterministic decode RPC coverage to assert Harmony filter and gRPC
     write counters are populated.
3. Add red control-plane tests.
   - Add an SSE writer test that consumes a token/completed stream and asserts
     `http.sse_write_*` counters are populated.
   - Extend the request-coordinator stream metrics test to assert
     `http.worker_event_handle_*` counters update while preserving fast token
     delivery.
4. Implement worker instrumentation.
   - Time `HarmonyChannelOutputFilter.accept` and `finish` calls once per
     filter invocation.
   - Time each `response.write` call in the decode/generate output path.
   - Record totals, counts, and averages at the end of successful requests.
5. Implement control-plane instrumentation.
   - Time each upstream worker event handling loop in `RequestCoordinator`.
   - Time each non-keepalive SSE frame emission in `SSEStreamWriter`.
   - Accumulate total/count locally and commit one metrics-store update when
     the stream task completes, avoiding per-frame actor hops in the hot path.
6. Update the three-way report and Python tests.
   - Add the new metric keys to the Melix metrics snapshot table.
   - Extend the Markdown unit test with representative values.

## Performance Probes And Success Metrics

- Worker instrumentation uses local `Date()` deltas and one metrics-store update
  group per completed request, not per-token actor hops.
- Control-plane event handling and SSE emission use local `DispatchTime` deltas
  on each event/frame, then write one aggregate metrics-store update at stream
  completion instead of awaiting the metrics actor per event/frame.
- The existing same-cohort batching probe should remain green because this slice
  is observational.
- A future Gemma E4B rerun should use these counters to decide whether #1660
  should optimize Harmony filtering, gRPC write cadence, control-plane event
  handling, SSE frame generation, or a lower-level runtime bucket.

## Verification

```bash
swift test --package-path services/mlx-text-worker-swift --enable-code-coverage --filter 'WorkerScaffoldTests/testMetricsStoreTracksCountersAndTimings|WorkerScaffoldTests/testDecodeStreamingRpcBatchesHomogeneousDeterministicDecodeRequests'

swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'SSEStreamWriterTests/recordsSSEWriteMetricsForDataFrames|RequestCoordinatorTests/firstTokenDeliveryIsNotBlockedBySchedulerProgressPublishing'

PYTHONPATH=$PWD:$PWD/scripts COVERAGE_FILE=.coverage.three_way uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest tests/test_three_way_serving_compare.py -q

PYTHONPATH=$PWD:$PWD/scripts COVERAGE_FILE=.coverage.three_way uv run --project services/mlx-worker-python --extra mlx coverage json -o coverage-three-way.json

python3 scripts/changed_scope_coverage.py --coverage-json coverage-three-way.json scripts/three_way_serving_compare.py tests/test_three_way_serving_compare.py

python3 scripts/same_cohort_batching_probe.py --metrics

git diff --check
```

## Metrics Report

Verification was run on June 1, 2026 from the
`codex/issue-1659-token-loop-counters-20260601` worktree.

- `swift test --package-path services/mlx-text-worker-swift --enable-code-coverage --filter 'WorkerScaffoldTests/testMetricsStoreTracksCountersAndTimings|WorkerScaffoldTests/testDecodeStreamingRpcBatchesHomogeneousDeterministicDecodeRequests|WorkerScaffoldTests/testGenerateSuppressesHarmonyThoughtChannelForLoadedModel'`
  - Result: passed, 3 tests, 0 failures.
- `uv run --project services/mlx-worker-python --extra mlx python scripts/swift_changed_line_coverage.py ... services/mlx-text-worker-swift/...`
  - Result: `TOTAL 98.26% 169/172`.
  - Remaining uncovered changed lines are decode-only branches for acceleration
    event write and cache-decision/snapshot writes.
- `swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'SSEStreamWriterTests/recordsSSEWriteMetricsForDataFrames|RequestCoordinatorTests/firstTokenDeliveryIsNotBlockedBySchedulerProgressPublishing'`
  - Result: passed, 2 Swift Testing tests, 0 issues.
  - Rerun after review fix: passed, 2 Swift Testing tests, 0 issues.
- `swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'SSEStreamWriterTests/recordsSSEWriteMetricsForDataFrames|SSEStreamWriterTests/emitsIdBearingCompletionForEmptyUpstream|SSEStreamWriterTests/emitsTransportErrors|RequestCoordinatorTests/firstTokenDeliveryIsNotBlockedBySchedulerProgressPublishing|RequestCoordinatorTests/streamFailuresPropagateAndReleaseRequestTracking'`
  - Result after review fix: passed, 5 Swift Testing tests, 0 issues.
- `uv run --project services/mlx-worker-python --extra mlx python scripts/swift_changed_line_coverage.py ... services/control-plane-swift/...`
  - Result before review fix: `TOTAL 95.79% 91/95`.
  - Result after review fix: `TOTAL 100.00% 33/33` for the changed
    control-plane lines since `HEAD`.
- `PYTHONPATH=$PWD:$PWD/scripts COVERAGE_FILE=.coverage.three_way uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest tests/test_three_way_serving_compare.py -q`
  - Result: passed, `44 passed in 0.07s`.
- `PYTHONPATH=$PWD:$PWD/scripts uv run --project services/mlx-worker-python --extra mlx python scripts/changed_scope_coverage.py --coverage-json coverage-three-way.json scripts/three_way_serving_compare.py tests/test_three_way_serving_compare.py`
  - Result: `TOTAL 12 0 100%`.
- `python3 scripts/same_cohort_batching_probe.py --metrics`
  - Result: exit 0 with `failure_count=0`, `status_warning=1`,
    `scheduler_admission_cohort_size=2`, and `worker_model_eval_batch_size=1`.
    This preserves the existing #1642 batching warning: admission coalesces the
    same-cohort requests, but worker/model-step evidence remains singleton. This
    instrumentation slice does not change batching behavior.
- `git diff --check`
  - Result: passed with no output.
