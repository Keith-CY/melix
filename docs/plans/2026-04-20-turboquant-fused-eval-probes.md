# TurboQuant Fused Eval Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use test-driven-development before modifying production code. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add measurement probes that separate TurboQuant fused attention graph-build/route cost from MLX lazy evaluation sync cost before attempting another speedup.

**Architecture:** Keep the default decode behavior unchanged. Add per-cache fused attention timing counters around the vendored q4 route, export them through `ActiveKVProbeSummary`, and add an opt-in model-eval sync probe that forces `eval(output.logits)` after each decode model call so the lazy GPU sync can be measured separately from token sampling.

**Tech Stack:** Swift MLX, vendored `mlx-swift-lm`, Python phase2 metrics report, real-model phase2 metrics JSON.

---

## Files

- Modify `third_party/mlx-swift-lm/Libraries/MLXLMCommon/KVCache.swift` to expose fused attention timing counters and a recording hook on `QuantizedKVCacheProtocol`.
- Modify `third_party/mlx-swift-lm/Libraries/MLXLMCommon/AttentionUtils.swift` to time the vendored fused route after `updateQuantizedStorage(...)`.
- Modify `services/mlx-text-worker-swift/Sources/Core/Runtime/TextRuntime.swift` to carry new active-KV probe fields.
- Modify `services/mlx-text-worker-swift/Sources/Core/Runtime/SwiftMLXBackend.swift` to collect cache fused-route totals and the opt-in `MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE=1` sync timing.
- Modify `services/mlx-text-worker-swift/Sources/Core/Inference/TextDecodeEngine.swift` and `services/mlx-text-worker-swift/Sources/Core/MetricsStore.swift` to export the new metrics.
- Modify `scripts/phase2_metrics_report.py` and `services/mlx-worker-python/tests/test_phase2_metrics_report.py` to preserve the new fields in decode rows, comparisons, release-gate evidence, and rendered tables.
- Modify `services/mlx-text-worker-swift/Tests/CoreTests/WorkerScaffoldTests.swift` for red/green Swift coverage.
- Add one real-model JSON under `docs/metrics/` after implementation.

## Probe Fields

- `active_kv_fused_attention_total_us`
- `active_kv_fused_attention_call_count`
- `active_kv_fused_attention_avg_us`
- `active_kv_fused_attention_route_total_us`
- `active_kv_fused_attention_route_avg_us`
- `active_kv_decode_model_eval_sync_total_us`
- `active_kv_decode_model_eval_sync_call_count`
- `active_kv_decode_model_eval_sync_avg_us`

## Tasks

- [x] **Task 1: RED Swift metrics export tests**
  - Add assertions that `MetricsStore` starts all new counters at zero.
  - Extend `testDecodeStreamingRpcRecordsActiveKVProbeSummary` so a synthetic `ActiveKVProbeSummary` exports non-zero fused attention and eval-sync values.
  - Expected RED command: `swift test --package-path services/mlx-text-worker-swift --filter 'WorkerScaffoldTests/testMetricsStoreTracksCountersAndTimings|WorkerScaffoldTests/testDecodeStreamingRpcRecordsActiveKVProbeSummary'`

- [x] **Task 2: RED vendored route timing test**
  - Extend the existing fused q4 attention storage-route test to assert `fusedAttentionCallCount == 1` and non-negative timing totals after `attentionWithCacheUpdate(...)`.
  - Expected RED command: `swift test --package-path services/mlx-text-worker-swift --filter WorkerScaffoldTests/testAttentionWithCacheUpdateUsesFusedQuantizedStorageWithoutMaterializingForDecode`

- [x] **Task 3: GREEN Swift probe implementation**
  - Add cache counters and recording hooks in `QuantizedKVCache`.
  - Time the `fusedQ4ScaledDotProductAttention(...)` route in `attentionWithCacheUpdate(...)`.
  - Add `MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE=1` handling in the decode loop and record `eval(output.logits)` sync time only when enabled.
  - Export all fields through `ActiveKVProbeSummary` and `TextDecodeEngine`.

- [x] **Task 4: RED/GREEN Python metrics report**
  - Add Python tests that phase2 JSON rows preserve all new fields and aggregate them into `active_kv_release_gates.turboquant_fused_decode.runtime_evidence`.
  - Implement the report changes after the tests fail.

- [x] **Task 5: Verification and real-model probe**
  - Run Swift targeted tests with coverage and changed-line coverage for touched Swift files.
  - Run Python report tests with coverage and changed-line coverage.
  - Run a real-model phase2 metrics JSON with `MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE=1`.
  - Re-run `--require-fused-turboquant`; keep the release gate blocked unless `worker_tps_overhead_pct <= 15` and `active_kv_kernel_path != fallback`.

## Verification Results

- Swift RED coverage was confirmed before implementation for the new metrics export and fused-route timing expectations.
- Python RED coverage was confirmed before implementation for the phase2 report additions.
- Swift targeted tests passed:
  `swift test --package-path services/mlx-text-worker-swift --filter 'WorkerScaffoldTests/testActiveKVModelEvalSyncProbeIsOptIn|WorkerScaffoldTests/testMetricsStoreTracksCountersAndTimings|WorkerScaffoldTests/testDecodeStreamingRpcRecordsActiveKVProbeSummary|WorkerScaffoldTests/testActiveKVProbeSummaryAveragesReturnZeroWithoutDecodeTokens|WorkerScaffoldTests/testAttentionWithCacheUpdateUsesFusedQuantizedStorageWithoutMaterializingForDecode|WorkerScaffoldTests/testAttentionWithCacheUpdateMaterializesQuantizedStorageWhenFusedRouteIsUnsupported|WorkerScaffoldTests/testVendoredFusedQ4AttentionMatchesQuantizedReferenceForDecodeGQA|WorkerScaffoldTests/testTurboQuantMetalCapabilityRunsMSEQ4FusedAttentionFromQuantizedKVCacheState|WorkerScaffoldTests/testTurboQuantRuntimeRouteReportsRoutedAfterFusedAttentionDispatch|WorkerScaffoldTests/testAutoSwiftMLXBackendDecodeReportsTurboQuantFusedRuntimeRoute|WorkerScaffoldTests/testQuantizedKVCacheRecordsUpdateAndMaterializeProbeTimings|WorkerScaffoldTests/testFusedDecodeQuantizerMatchesReferenceForSingleTokenAffineQ4|WorkerScaffoldTests/testFusedDecodeQuantizerMatchesReferenceForSingleTokenBFloat16AffineQ4|WorkerScaffoldTests/testFusedDecodeQuantizerRejectsUnsupportedInputs|WorkerScaffoldTests/testQuantizedKVCacheUsesNativeDecodeQuantizerByDefaultForSingleTokenAffineQ4|WorkerScaffoldTests/testQuantizedKVCacheUsesFusedDecodeQuantizerWhenExplicitlyEnabledForSingleTokenAffineQ4'`.
- Swift changed-line coverage for touched Swift files was `97.78%` total. `SwiftMLXBackend.swift` was `90.91%` because the real decode-loop counter increment branch is exercised by the real-model probe rather than the synthetic unit tests.
- Python combined tests passed:
  `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest services/mlx-worker-python/tests/test_phase2_metrics_report.py services/mlx-worker-python/tests/test_dev_up_script.py -q`, reporting `55 passed`.
- Python changed-line coverage for `scripts/phase2_metrics_report.py`, `scripts/dev_up.py`, and their touched tests was `100.00%` total.
- Real-model evidence was written to `docs/metrics/phase2-active-kv-vendored-turboquant-eval-probe.json` using `mlx-community/Qwen3.5-0.8B-OptiQ-4bit` from the local Hugging Face cache and `MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE=1`.
- The explicit fused release gate remains blocked. The JSON reports `active_kv_kernel_path = "fallback"`, `active_kv_runtime_route = "blocked"`, `active_kv_runtime_block_reason = "unsupported_cache_state"`, `active_kv_fallback_count = 3`, `active_kv_estimated_memory_savings_pct = 0.0`, and `worker_tps_overhead_pct = 0.0`.
- The eval-sync probe reports `decode_model_eval_sync_total_us = 4311359` over `189` calls, with comparison median `active_kv_decode_model_eval_sync_avg_us = 22607`. Fused attention totals remain zero because the Qwen3.5 run never enters the vendored fused route.
