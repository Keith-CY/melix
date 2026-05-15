# TurboQuant Q4 Active-KV Default

## Goal

Make the user-facing 4-bit active-KV path select the routed TurboQuant Q4
profile instead of silently falling back to affine q4 cache quantization.

## Scope

- Keep affine `q4` available for explicit comparison probes.
- Make empty active-KV profile requests normalize to `turboquant-q4`.
- Keep named serving acceleration profile IDs separate from active-KV quant
  profile IDs; serving profiles such as `balanced` must not become worker
  `activeKvQuantProfile` values.
- Advertise `turboquant-q4` in worker active-KV capabilities.
- Preserve the existing fused-route source of truth:
  `active_kv_kernel_path != fallback`,
  `active_kv_runtime_route = routed`,
  and non-zero fused attention dispatch counters.
- Keep Phase 2 release-gate verification as the product evidence path.

## Measurement Points

- Worker handshake cache profiles and `active_kv_quantized` capability metadata.
- Applied acceleration policy on prefill/decode events.
- Runtime metrics:
  - `swift_text.active_kv_backend_code`
  - `swift_text.active_kv_kernel_path_code`
  - `swift_text.active_kv_runtime_route_code`
  - `swift_text.active_kv_fused_attention_call_count`
  - `swift_text.active_kv_estimated_memory_savings_pct`
- Phase 2 metrics:
  `swift_worker_direct.active_kv_release_gates.turboquant_fused_decode`.

## Success Metrics

- Empty active-KV profile normalizes to `turboquant-q4`.
- The worker advertises `turboquant-q4` as the first active-KV profile.
- Explicit `q4` remains an affine profile and still reports q4 memory ratio.
- Explicit active-KV quant profile IDs such as `q8` remain supported, while
  named serving acceleration profiles fall back to the default quant profile.
- Existing TurboQuant fused-route tests continue to prove route promotion only
  after a real fused attention dispatch.
- `scripts/phase2_metrics_report.py --require-fused-turboquant` remains the
  acceptance gate for real-model evidence.

## Verification

- `xcrun swift test --package-path services/mlx-text-worker-swift --filter 'WorkerScaffoldTests/testHandshakeReturnsExpectedRuntimeMetadata|WorkerScaffoldTests/testActiveKVDefaultProfileNormalizesToTurboQuantQ4|WorkerScaffoldTests/testAutoSwiftMLXBackendPrefillNormalizesActiveKVProfileForLiveBridge|WorkerScaffoldTests/testPrefillReturnsActiveKVQuantizationRatioAndNormalizedProfile|WorkerScaffoldTests/testDiskCacheQuantizationHelpersClampAndNormalizeProfiles|WorkerScaffoldTests/testTurboQuantActiveKVUsesVendoredRuntimeWithoutProbe|WorkerScaffoldTests/testTurboQuantRuntimeRouteReportsRoutedAfterFusedAttentionDispatch'`
- `swift test --package-path services/control-plane-swift --filter RequestCoordinatorTests`
- `xcrun swift test --package-path services/mlx-text-worker-swift --enable-code-coverage --filter 'WorkerScaffoldTests/testHandshakeReturnsExpectedRuntimeMetadata|WorkerScaffoldTests/testActiveKVDefaultProfileNormalizesToTurboQuantQ4|WorkerScaffoldTests/testAutoSwiftMLXBackendPrefillNormalizesActiveKVProfileForLiveBridge|WorkerScaffoldTests/testPrefillReturnsActiveKVQuantizationRatioAndNormalizedProfile|WorkerScaffoldTests/testDiskCacheQuantizationHelpersClampAndNormalizeProfiles|WorkerScaffoldTests/testTurboQuantActiveKVUsesVendoredRuntimeWithoutProbe|WorkerScaffoldTests/testTurboQuantRuntimeRouteReportsRoutedAfterFusedAttentionDispatch'`
- `swift test --package-path services/control-plane-swift --enable-code-coverage --filter RequestCoordinatorTests`
- `python3.11 scripts/swift_changed_line_coverage.py ...`
