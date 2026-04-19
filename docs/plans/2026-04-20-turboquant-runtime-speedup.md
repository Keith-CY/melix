# TurboQuant Runtime Speedup Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use test-driven-development before modifying production code. Keep probe changes measurable before relying on an optimization.

**Goal:** Reduce `turboquant-q4` decode overhead after the Qwen3.5 hybrid cache route is already using the vendored fused attention path.

**Current evidence:** `docs/metrics/phase2-active-kv-qwen35-hybrid-stability-summary.json` shows five routed Qwen3.5 runs with `worker_tps_overhead_pct` min/median/mean/max of `5.71 / 10.26 / 9.722 / 12.82`. The route is stable, but `decode_model_eval_sync_total_us` dominates the profile (`3.57s-4.13s`), while fused attention totals are only `216ms-229ms` across `1134` calls. The next optimization must therefore be small and measured against real-model noise.

## Hypothesis

The first probe hypothesis was that the fused q4 decode attention launch reserved inactive lanes for Qwen3.5. The pre-optimization JSON disproved that for this model: active lanes and launched lanes were both `12096`, so launch-width tightening would not help Qwen3.5.

The applied optimization targets duplicated per-token work inside the 32 active lanes:

- compute the online-softmax `exp`, max, normalizer, and weight only on lane 0, then broadcast `weight` and `rescale` to value lanes;
- hoist each lane's eight query values out of the historical-token loop.

## Success Metrics

- `active_kv_kernel_path != fallback`
- `active_kv_runtime_route == routed`
- `active_kv_fallback_count == 0`
- `worker_tps_overhead_pct <= 15`
- `active_kv_fused_attention_softmax_token_lane_total` decreases after the single-lane softmax optimization.

## Tasks

- [x] **Task 1: Probe the fused attention launch shape**
  - Add per-run metrics for fused q4 attention active lane total, launched lane total, softmax lane total, and softmax token-lane total.
  - Keep the launch and softmax behavior unchanged for the first probe run.
  - Capture a Qwen3.5 real-model pre-optimization JSON with the new lane probes.

- [x] **Task 2: Optimize duplicated fused decode softmax work**
  - Keep the 32-lane launch width for Qwen3.5 because the pre-optimization probe shows no inactive launched lanes.
  - Change the fused q4 decode kernel so online-softmax state is computed on one lane and broadcast to value lanes.
  - Hoist per-lane query values out of the historical-token loop.
  - Keep unsupported shapes on the existing fallback path.
  - Add unit coverage proving launch plans, metrics propagation, and GQA decode outputs remain correct.

- [x] **Task 3: Verify and compare**
  - Run targeted Swift tests for TurboQuant attention and metrics propagation.
  - Run changed-scope Swift coverage for touched files.
  - Capture a Qwen3.5 real-model post-optimization JSON and compare it with the pre-optimization JSON.
  - Keep the release gate enabled only if the post-optimization JSON still passes the TurboQuant gate.

- [x] **Task 4: Codify repeated-run release evidence**
  - Add a Phase 2 metrics stability-summary mode that reads ordered raw run JSONs.
  - Preserve leading warmup runs while excluding them from `pass_count`, `run_count`, and aggregate statistics.
  - Make `--require-fused-turboquant` fail unless the measured runs satisfy the required run count, non-fallback route, routed runtime, and worker-overhead threshold.

## Evidence

- Pre-optimization JSON: `docs/metrics/phase2-active-kv-qwen35-turboquant-speedup-preopt.json`.
- Post-optimization JSON: `docs/metrics/phase2-active-kv-qwen35-turboquant-speedup-postopt.json`.
- The pre-optimization probe disproved the launch-width hypothesis for Qwen3.5: active lanes `12096`, launched lanes `12096`, inactive lanes `0`.
- The final post-optimization run reduces softmax token-lane work from `641088` to `20034` while preserving active/launched lanes at `12096`.
- Qwen3.5 post-optimization release gate passes with `active_kv_kernel_path = tq_mse_single`, `active_kv_runtime_route = routed`, `active_kv_fallback_count = 0`, and `worker_tps_overhead_pct = 5.13`.
- Comparison row moved from pre-opt `worker_tps_overhead_pct = 17.5`, `wall_tps_overhead_pct = 17.88`, `active_kv_fused_attention_avg_us = 201`, `active_kv_decode_model_eval_sync_avg_us = 21726` to post-opt `5.13`, `7.28`, `191`, and `19300`. Treat the TPS delta as noisy single-run evidence; the softmax token-lane reduction is the deterministic optimization evidence.
- Stability summary JSON: `docs/metrics/phase2-active-kv-qwen35-turboquant-speedup-stability-summary.json`.
- The stability rerun used the same `MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE=1` timing mode as the speedup JSONs and records one warmup run followed by five measured runs. The warmup is preserved but excluded from aggregate release evidence. The measured runs report `pass_count = 5`, `run_count = 5`, `all_non_fallback = true`, `all_routed = true`, and `all_worker_overhead_within_threshold = true`. `worker_tps_overhead_pct` min/median/mean/max is `10.0 / 10.26 / 11.044 / 12.5`, so the speedup has repeated-run release-gate pass evidence under the warmup protocol.
- The committed stability summary is generated by `scripts/phase2_metrics_report.py --stability-input-json ... --stability-warmup-count 1 --stability-required-runs 5 --require-fused-turboquant`, not by hand-editing the summary JSON.

## Verification

- `jq empty docs/metrics/phase2-active-kv-qwen35-turboquant-speedup-preopt.json docs/metrics/phase2-active-kv-qwen35-turboquant-speedup-postopt.json`
- `make phase2-metrics PHASE2_METRICS_ARGS='--input-json docs/metrics/phase2-active-kv-qwen35-turboquant-speedup-postopt.json --json --require-fused-turboquant'`
- `uv run --project services/mlx-worker-python python scripts/phase2_metrics_report.py --stability-input-json /tmp/melix-phase2-qwen35-tq-speedup-warmup-stability/warmup.json --stability-input-json /tmp/melix-phase2-qwen35-tq-speedup-warmup-stability/measured-1.json --stability-input-json /tmp/melix-phase2-qwen35-tq-speedup-warmup-stability/measured-2.json --stability-input-json /tmp/melix-phase2-qwen35-tq-speedup-warmup-stability/measured-3.json --stability-input-json /tmp/melix-phase2-qwen35-tq-speedup-warmup-stability/measured-4.json --stability-input-json /tmp/melix-phase2-qwen35-tq-speedup-warmup-stability/measured-5.json --stability-warmup-count 1 --stability-required-runs 5 --stability-model mlx-community/Qwen3.5-0.8B-OptiQ-4bit --stability-runtime-dir /tmp/melix-phase2-qwen35-tq-speedup-warmup-stability-runtime --stability-output-dir /tmp/melix-phase2-qwen35-tq-speedup-warmup-stability --stability-committed-summary-path docs/metrics/phase2-active-kv-qwen35-turboquant-speedup-stability-summary.json --stability-probe-env MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE=1 --output docs/metrics/phase2-active-kv-qwen35-turboquant-speedup-stability-summary.json --require-fused-turboquant`
- `swift test --package-path services/mlx-text-worker-swift --enable-code-coverage --filter 'WorkerScaffoldTests/testDecodeStreamingRpcRecordsActiveKVProbeSummary|WorkerScaffoldTests/testAttentionWithCacheUpdateUsesFusedQuantizedStorageWithoutMaterializingForDecode|WorkerScaffoldTests/testVendoredFusedQ4AttentionLaunchPlanUsesOnlineSoftmaxAcrossValueLanes|WorkerScaffoldTests/testVendoredFusedQ4AttentionMatchesQuantizedReferenceForDecodeGQA|WorkerScaffoldTests/testTurboQuantMetalCapabilityRunsMSEQ4FusedAttentionFromQuantizedKVCacheState|WorkerScaffoldTests/testAutoSwiftMLXBackendDecodeReportsTurboQuantFusedRuntimeRoute|WorkerScaffoldTests/testAutoSwiftMLXBackendDecodeUsesVendoredTurboQuantRouteWhenProbeIsDisabled'`: 7 tests, 0 failures.
- `python3 scripts/swift_changed_line_coverage.py ...`: changed-line coverage `100.00% (109/109)` for touched Swift source and tests.
- `PYTHONPATH=... uv run --project services/mlx-worker-python coverage run -m pytest services/mlx-worker-python/tests/test_phase2_metrics_report.py -k 'active_kv or repeats_decode_profiles or stability' -q`: 20 tests passed, 13 deselected.
- `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/melix_tq_speedup_python_coverage.json scripts/phase2_metrics_report.py services/mlx-worker-python/tests/test_phase2_metrics_report.py`: changed-line coverage `100.00% (227/227)` for touched Python source and tests.
- `git diff --check`

## Notes

- Do not enable the rejected fused decode-quantize path by default; earlier evidence showed it regressed `cache_quantize_total_us`.
- Do not change the attention hook/runtime route policy in this slice; the route is already non-fallback for Qwen3.5 after mixed-cache quantization.
- Review follow-up kept the runtime policy intact while tightening evidence and guard rails:
  - HF cache snapshot fallback now emits a warning when `refs/main` is unavailable and the resolver falls back to lexicographic snapshot selection.
  - The vendored fused q4 attention kernel now returns the query dtype, including bfloat16 decode queries.
  - Prior fused dispatch evidence now reports the route as `routed` before rechecking cache state, avoiding misleading blocked metrics after a successful dispatch.
  - Dead TurboQuant affine-fallback plumbing and unused candidate-probe arguments were removed from runtime quantization enablement.
  - The vendored patch notes now document the single-lane online-softmax constraint and the fused decode quantizer's scoped tuple contract.
- Review follow-up verification:
  - `env PYTHONPATH=/Users/ChenYu/Documents/Github/melix/.worktrees/turboquant-probes uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_phase2_metrics_report.py -k "hf_cache_snapshot or turboquant_fused_probe" -q`: 2 tests passed.
  - `swift test --package-path services/mlx-text-worker-swift --filter 'WorkerScaffoldTests/testVendoredFusedQ4AttentionPreservesQueryDTypeForDecodeGQA|WorkerScaffoldTests/testFusedDecodeQuantizerDefaultReadsInjectedEnvironment|WorkerScaffoldTests/testTurboQuantRuntimeRouteReportsRoutedFromDispatchEvidenceBeforeStateRecheck|WorkerScaffoldTests/testTurboQuantActiveKVUsesVendoredRuntimeWithoutProbe'`: 4 tests passed.
  - `swift test --package-path services/mlx-text-worker-swift --enable-code-coverage --filter 'WorkerScaffoldTests/testDecodeStreamingRpcRecordsActiveKVProbeSummary|WorkerScaffoldTests/testAttentionWithCacheUpdateUsesFusedQuantizedStorageWithoutMaterializingForDecode|WorkerScaffoldTests/testVendoredFusedQ4AttentionLaunchPlanUsesOnlineSoftmaxAcrossValueLanes|WorkerScaffoldTests/testVendoredFusedQ4AttentionMatchesQuantizedReferenceForDecodeGQA|WorkerScaffoldTests/testVendoredFusedQ4AttentionPreservesQueryDTypeForDecodeGQA|WorkerScaffoldTests/testTurboQuantMetalCapabilityRunsMSEQ4FusedAttentionFromQuantizedKVCacheState|WorkerScaffoldTests/testAutoSwiftMLXBackendDecodeReportsTurboQuantFusedRuntimeRoute|WorkerScaffoldTests/testAutoSwiftMLXBackendDecodeUsesVendoredTurboQuantRouteWhenProbeIsDisabled|WorkerScaffoldTests/testAutoSwiftMLXBackendDecodeCanLazilyQuantizeBaselinePrefillCache|WorkerScaffoldTests/testFusedDecodeQuantizerDefaultReadsInjectedEnvironment|WorkerScaffoldTests/testTurboQuantRuntimeRouteReportsRoutedAfterFusedAttentionDispatch|WorkerScaffoldTests/testTurboQuantRuntimeRouteReportsRoutedFromDispatchEvidenceBeforeStateRecheck|WorkerScaffoldTests/testTurboQuantActiveKVUsesVendoredRuntimeWithoutProbe|WorkerScaffoldTests/testFusedDecodeQuantizerMatchesReferenceForSingleTokenBFloat16AffineQ4|WorkerScaffoldTests/testQuantizedKVCacheUsesFusedDecodeQuantizerWhenExplicitlyEnabledForSingleTokenAffineQ4'`: 15 tests passed.
  - `python3 scripts/swift_changed_line_coverage.py ...`: touched Swift changed-line coverage `98.80% (82/83)`.
  - `env PYTHONPATH=/Users/ChenYu/Documents/Github/melix/.worktrees/turboquant-probes COVERAGE_FILE=/tmp/melix_review_python.coverage uv run --project services/mlx-worker-python coverage run -m pytest services/mlx-worker-python/tests/test_phase2_metrics_report.py -k "hf_cache_snapshot or active_kv_fused_candidate_probe or main_backfills_fused_candidate_probe" -q`: 6 tests passed.
  - `python3 scripts/python_changed_line_coverage.py ...`: touched Python changed-line coverage `100.00% (22/22)`.
  - `git diff --check`
