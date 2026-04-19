# Qwen3.5 Hybrid Cache TurboQuant Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use test-driven-development before modifying production code. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Qwen3.5 hybrid cache layouts quantize supported full-attention KV layers so `turboquant-q4` can enter the vendored fused attention route when the cache state is otherwise supported.

**Architecture:** Keep Mamba/linear-attention cache entries unmodified. Change active-KV quantization eligibility from "the first cache entry is quantizable" to "any KVCacheSimple entry is eligible", and update dynamic quantization to scan layer-by-layer instead of returning early on a leading unsupported cache. Continue to release-gate on real-model metrics; this slice may unblock Qwen3.5 routing but must not unblock the release gate unless the same JSON also reports `worker_tps_overhead_pct <= 15`.

**Tech Stack:** Swift MLX, vendored `mlx-swift-lm`, Melix Swift worker probes, Python phase2 metrics JSON.

---

## Root Cause

Qwen3.5 creates a hybrid cache array: linear-attention layers use `MambaCache()`, while full-attention layers use `KVCacheSimple()`. The current `maybeQuantizeKVCache(...)` exits based only on `cache[0]`, requiring the first cache entry to have an offset past `quantizedKVStart` and not already be quantized. Because Qwen3.5 starts with a `MambaCache`, supported full-attention `KVCacheSimple` entries later in the array never become `QuantizedKVCache`.

## Files

- Modify `third_party/mlx-swift-lm/Libraries/MLXLMCommon/KVCache.swift` so `maybeQuantizeKVCache(...)` scans cache entries independently and quantizes each eligible `KVCacheSimple`.
- Modify `services/mlx-text-worker-swift/Sources/Core/Runtime/SwiftMLXBackend.swift` so `shouldAttemptActiveKVDecodeQuantization(...)` detects any eligible `KVCacheSimple` in mixed cache arrays.
- Modify `services/mlx-text-worker-swift/Tests/CoreTests/WorkerScaffoldTests.swift` with RED/GREEN coverage for mixed Qwen3.5-style cache arrays.
- Update `docs/architecture/2026-04-18-turboquant-kv-cache-optimization.md`, `docs/plans/2026-03-30-m6-7-kv-cache-quantization-acceleration.md`, and `third_party/mlx-swift-lm/MELIX_PATCHES.md` after real-model evidence is captured.
- Add a real-model metrics JSON under `docs/metrics/` after implementation.

## Tasks

- [x] **Task 1: RED mixed-cache eligibility tests**
  - Add a unit test proving `shouldAttemptActiveKVDecodeQuantization(...)` returns true when a later `KVCacheSimple` is eligible even if `cache[0]` is `MambaCache`.
  - Add a unit test proving `maybeQuantizeKVCache(...)` preserves `MambaCache` entries and converts eligible `KVCacheSimple` entries to `QuantizedKVCacheProtocol`.
  - Expected RED commands:
    - `swift test --package-path services/mlx-text-worker-swift --filter WorkerScaffoldTests/testActiveKVDecodeQuantizationGuardDetectsEligibleSimpleLayerAfterMambaCache`
    - `swift test --package-path services/mlx-text-worker-swift --filter WorkerScaffoldTests/testMaybeQuantizeKVCacheQuantizesSimpleLayerAfterMambaCache`

- [x] **Task 2: GREEN mixed-cache quantization**
  - Update `maybeQuantizeKVCache(...)` to return only when `kvBits` is nil or the cache is empty; loop through entries and convert each eligible `KVCacheSimple` whose offset is greater than `quantizedKVStart`.
  - Update `shouldAttemptActiveKVDecodeQuantization(...)` to scan for any unquantized `KVCacheSimple` whose offset is greater than `quantizedKVStart`.
  - Keep quantized, Mamba, rotating, and composite cache entries unchanged.

- [x] **Task 3: Verification and real-model evidence**
  - Run the new targeted Swift tests and the existing TurboQuant targeted Swift set.
  - Run Swift changed-line coverage for touched Swift files.
  - Run the Qwen3.5 real-model phase2 metrics command with `MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE=1`.
  - Run `--require-fused-turboquant` against the new JSON; keep the release gate blocked unless `active_kv_kernel_path != fallback` and `worker_tps_overhead_pct <= 15`.

- [x] **Task 4: Documentation and handoff**
  - Record the real-model result in the architecture doc and M6.7 plan.
  - Update `MELIX_PATCHES.md` to document mixed-cache dynamic quantization behavior.
  - Commit and push after verification.

## Evidence So Far

- RED was confirmed with
  `swift test --package-path services/mlx-text-worker-swift --filter 'WorkerScaffoldTests/testActiveKVDecodeQuantizationGuardDetectsEligibleSimpleLayerAfterMambaCache|WorkerScaffoldTests/testMaybeQuantizeKVCacheQuantizesSimpleLayerAfterMambaCache'`, which failed because the guard returned false and `maybeQuantizeKVCache(...)` did not convert the later `KVCacheSimple`.
- GREEN was confirmed with the same command after per-layer scanning was implemented; both tests passed.
- The targeted TurboQuant Swift set passed with code coverage enabled:
  `swift test --package-path services/mlx-text-worker-swift --enable-code-coverage --filter 'WorkerScaffoldTests/testActiveKVDecodeQuantizationGuardSkipsWhenCacheIsAlreadyQuantized|WorkerScaffoldTests/testActiveKVDecodeQuantizationGuardDetectsEligibleSimpleLayerAfterMambaCache|WorkerScaffoldTests/testMaybeQuantizeKVCacheQuantizesSimpleLayerAfterMambaCache|WorkerScaffoldTests/testAttentionWithCacheUpdateUsesFusedQuantizedStorageWithoutMaterializingForDecode|WorkerScaffoldTests/testTurboQuantRuntimeRouteReportsRoutedAfterFusedAttentionDispatch|WorkerScaffoldTests/testAutoSwiftMLXBackendDecodeReportsTurboQuantFusedRuntimeRoute'`.
- Changed-line coverage for the touched Swift files is 100.00% (`73/73`) across `SwiftMLXBackend.swift`, vendored `KVCache.swift`, and `WorkerScaffoldTests.swift`.
- Real-model Qwen3.5 evidence was written to `docs/metrics/phase2-active-kv-qwen35-hybrid-turboquant-routing.json` using `mlx-community/Qwen3.5-0.8B-OptiQ-4bit` from the local Hugging Face cache and `MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE=1`.
- `--require-fused-turboquant` exits zero for that JSON. The release gate reports `status = "pass"`, `active_kv_kernel_path = "tq_mse_single"`, `active_kv_runtime_route = "routed"`, `active_kv_fallback_count = 0`, `active_kv_estimated_memory_savings_pct = 75.0`, `fused_attention_call_count = 1134`, and `worker_tps_overhead_pct = 12.82`.
- Stability evidence was added in `docs/metrics/phase2-active-kv-qwen35-hybrid-stability-summary.json`. It summarizes five sequential Qwen3.5 `turboquant-q4` runs, each checked with `--require-fused-turboquant`; all five pass, all five route through `tq_mse_single`, all five report `active_kv_fallback_count = 0`, and `worker_tps_overhead_pct` min/median/mean/max is `5.71 / 10.26 / 9.722 / 12.82`.
- `jq empty docs/metrics/phase2-active-kv-qwen35-hybrid-turboquant-routing.json` and `git diff --check` both exit zero.
