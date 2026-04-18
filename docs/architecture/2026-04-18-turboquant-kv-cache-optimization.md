# TurboQuant KV Cache Optimization

## Context

Melix active-KV quantization is opt-in and currently runs through Swift MLX LM's
`QuantizedKVCache` path. That path gives measurable KV memory reduction, but it
does not implement the oMLX TurboQuant fused decode architecture.

The current benchmark evidence is:

| Evidence | File | Model | Profiles |
| --- | --- | --- | --- |
| Pre-optimization baseline | `docs/metrics/phase2-affine-q4-preopt.json` | `mlx-community/Qwen3-0.6B-4bit` | `q4` |
| Decode-guard post-optimization | `docs/metrics/phase2-active-kv-decode-guard-postopt.json` | `mlx-community/Qwen3-0.6B-4bit` | `q4`, `turboquant-q4` |
| Runtime speedup post-optimization | `docs/metrics/phase2-active-kv-runtime-speedup-postopt.json` | `mlx-community/Qwen3-0.6B-4bit` | `q4`, `turboquant-q4` |
| Fused TurboQuant candidate audit | `docs/metrics/phase2-active-kv-fused-turboquant-candidate.json` | `mlx-community/Qwen3-0.6B-4bit` | `q4`, `turboquant-q4` |

`mlx-community/Qwen3.5-0.8B-OptiQ-4bit` remains the shared Phase 8 real-model
E2E convention. The active-KV Swift benchmark uses Qwen3-0.6B because the pinned
Swift MLXLLM registry does not yet support `model_type = qwen3_5`.

## External Reference Findings

oMLX v0.3.4 reports the relevant target shape: `BatchTurboQuantKVCache` was
rewritten as a `TurboQuantKVCache` subclass, and fused Metal kernels combined
score, softmax, and value into one decode dispatch. The release reports decode
overhead dropping from 43 percent to 8 percent vs baseline for the referenced
Qwen3.5-4B run.

The oMLX code keeps `omlx/turboquant_kv.py` as a thin public API layer around
`mlx_vlm.turboquant`. `BatchTurboQuantKVCache` inherits the single-request
`TurboQuantKVCache` decode logic and adds only batch operations such as
merge, extract, extend, filter, and left-padding mask handling.

The oMLX attention patch changes `scaled_dot_product_attention` routing. For a
TurboQuant cache and a single query token, it calls `cache.decode_attention(...)`.
For prefill it tries `cache.prefill_attention(...)`, then falls back to
dequantize plus normal MLX SDPA if no quantized prefill path is available.

The MLX-VLM implementation has the actual kernels. Its `TurboQuantKVCache`:

- initializes deterministic key and value codecs from bit width and seed
- uses fused key+value quantization for single-token decode appends when possible
- stores packed quantized state instead of materialized FP16 history
- routes single-token decode through fused MSE decode, two-pass decode, separate
  score/value decode, or compiled integer fallback paths
- contains a fully fused Metal path that performs score, online softmax, value
  accumulation, normalization, and rotation in one dispatch

Sources:

- https://github.com/jundot/omlx/releases/tag/v0.3.4
- https://github.com/jundot/omlx/blob/main/omlx/turboquant_kv.py
- https://github.com/jundot/omlx/blob/main/omlx/patches/turboquant_attention.py
- https://github.com/Blaizzy/mlx-vlm/blob/main/mlx_vlm/turboquant.py

## Current Melix Gap

Melix exposes a `turboquant-q4` profile for probes, but the runtime still uses
Swift MLX LM affine `QuantizedKVCache`. The post-optimization probe correctly
reports:

- `decode_affine_q4`: backend `affine`, kernel path `affine_quantized_sdpa`
- `decode_turboquant_q4`: backend `turboquant`, kernel path `fallback`, with
  `active_kv_fallback_count = 1`

That means the profile is observable, but not yet backed by a fused TurboQuant
cache or kernel. Treating it as a real TurboQuant fast path would be misleading
until the kernel path is no longer `fallback`.

## Implemented Optimization

This slice adds a decode-side guard:

- `shouldAttemptActiveKVDecodeQuantization(...)` checks active-KV mode, `kvBits`,
  cache offset, and whether the first cache is already `QuantizedKVCacheProtocol`
- the decode loop calls `maybeQuantizeKVCache(...)` only while that call can
  still mutate the cache
- after the cache becomes quantized, later decode tokens skip the maintenance call

This removes redundant Melix-side quantization maintenance during decode. It does
not change the attention kernel, storage layout, or quantization algorithm.

This slice also adds release-gate instrumentation for the next fused-kernel
phase:

- `turboquant-q4` fallback probes now report a non-zero fallback count
- `scripts/phase2_metrics_report.py` writes
  `swift_worker_direct.active_kv_release_gates.turboquant_fused_decode`
- `--require-fused-turboquant` exits non-zero when the TurboQuant probe is
  missing, reports a fallback or unknown kernel path, records fallback use,
  records decode-side quantization maintenance, or lacks the expected memory
  savings evidence

A follow-up feasibility slice proves the Swift text worker target can compile
and dispatch a custom `MLXFast.metalKernel(...)` kernel:

- `MelixTextWorkerCore` now depends explicitly on the `MLX` and `MLXFast`
  products from `mlx-swift`
- `TurboQuantMetalKernelCapability.runIdentitySmokeKernel(...)` dispatches a
  one-output identity kernel through the same custom Metal surface needed by a
  fused TurboQuant decode kernel
- `TurboQuantMetalKernelCapability.runMSEQ4ValueDecodeSmokeKernel(...)`
  dispatches an isolated packed-q4 value decode plus attention-weight
  accumulation kernel for a single query token
- `TurboQuantMetalKernelCapability.runMSEQ4FusedAttentionSmokeKernel(...)`
  dispatches an isolated packed-q4 key score, stable softmax, and value
  accumulation kernel for a single query token in one custom Metal dispatch
- `WorkerScaffoldTests.testTurboQuantMetalCapabilityRunsCustomIdentityKernel`
  `WorkerScaffoldTests.testTurboQuantMetalCapabilityRunsMSEQ4ValueDecodeKernel`,
  `WorkerScaffoldTests.testTurboQuantMetalCapabilityRunsMSEQ4FusedAttentionKernel`,
  and
  `WorkerScaffoldTests.testTurboQuantMetalCapabilityRunsMSEQ4FusedAttentionFromQuantizedKVCacheState`
  run the kernels under the existing temporary `default.metallib` fixture;
  `WorkerScaffoldTests.testTurboQuantMetalCapabilityRejectsUnsupportedQuantizedKVCacheStateInputs`
  keeps the affine-q4 guard rails explicit before runtime routing is promoted.
  These tests skip only when no local MLX metallib is available.

This does not route runtime decode through a new TurboQuant cache. The fused
attention smoke kernel intentionally favors capability and correctness over the
final parallel layout, so it removes uncertainty around whether the current
Swift package can host custom Metal kernels for packed-q4 score, softmax, and
value work without claiming an optimized runtime path.

The second runtime-candidate slice keeps
`active_kv_candidate_dispatch_code = 1` as "a candidate dispatch ran", but now
prefers a live `QuantizedKVCache` state over the fixed smoke arrays. The
candidate helper slices the first batch/head from MLXLM's affine q4 cache tuple
and decodes MLX's `uint32` bit-packed q4 layout in one Metal dispatch for
score, softmax, and value. If no supported cache state is available, the decode
probe falls back to the original fixed smoke arrays.

The runtime route decision is now explicit. Even when a live q4 cache can feed
the fused candidate kernel, Melix reports the TurboQuant runtime route as
blocked with `attentionHookUnavailable`. The reason is structural: Qwen/Llama
model attention in the pinned `mlx-swift-lm` package calls dependency-owned
`MLXLMCommon.attentionWithCacheUpdate(...)`, and Melix currently can only pass a
cache object into that function. It cannot replace the dependency's quantized
attention call from this target without a vendored dependency patch, upstream
hook, or Melix-owned model implementation.

The same route decision is exported into metrics as `active_kv_runtime_route`
and `active_kv_runtime_block_reason`. Current fallback reports should show the
route blocked by the missing attention hook, which makes the release evidence
auditable without treating candidate dispatch as runtime success.

The default runtime keeps candidate dispatch disabled while the route is
blocked. `active_kv_candidate_eligibility_check_count` measures the remaining
candidate-check work in the decode loop; the current optimized default path
precomputes whether a candidate probe can run and reports zero checks unless
`MELIX_SWIFT_TURBOQUANT_CANDIDATE_PROBE=1` is set before worker startup.

This still deliberately keeps `active_kv_kernel_path = "fallback"` until model
attention is actually routed through a fused TurboQuant cache. Model logits
still come from the Swift MLX model path, so the release gate remains blocked
until the post-run JSON shows both a non-fallback kernel path and
`worker_tps_overhead_pct <= 15`.

The first runtime-speedup slice removes the candidate dispatch from the default
blocked route. `MELIX_SWIFT_TURBOQUANT_CANDIDATE_PROBE=1` now explicitly opts
into the live fused-candidate probe; without that flag, `turboquant-q4` still
reports the blocked route and fallback kernel path, but it does not pay for a
custom Metal dispatch that cannot affect model logits. `scripts/dev_up.py`
passes the probe flag through to the Swift worker and writes it into `env.sh`
only when the parent environment sets it, so normal runtime paths stay
measurement-clean while candidate-audit runs remain reproducible.

This is a small runtime cleanup, not the real TurboQuant decode architecture.
The new default real-model run confirms candidate dispatch count drops from
five to zero, but the worker throughput overhead remains 45.76 percent because
the dependency-owned quantized attention model call is still the hot path.

## Before And After Metrics

The current runs used:

- model path: `/Users/ChenYu/.cache/huggingface/hub/models--mlx-community--Qwen3-0.6B-4bit/snapshots/73e3e38d981303bc594367cd910ea6eb48349da8`
- model revision: `main`
- prompt: `Continue this sentence with five short words: Melix measures cache speed by`
- decode repeats: `5`
- abort probe: skipped
- Swift worker metallib: explicit `mlx_metal` 0.29.1 `mlx.metallib`, matching
  `mlx-swift` 0.29.1 in `Package.resolved`

| Metric | Pre affine q4 | Post affine q4 | Default turboquant-q4 | Probe-mode turboquant-q4 |
| --- | ---: | ---: | ---: | ---: |
| Baseline worker decode tok/s | 65.0 | 59.0 | 59.0 | 58.0 |
| Active worker decode tok/s | 38.0 | 32.0 | 32.0 | 32.0 |
| Worker TPS overhead | 41.54% | 45.76% | 45.76% | 44.83% |
| Baseline wall tok/s | 65.75 | 59.43 | 59.43 | 58.90 |
| Active wall tok/s | 38.35 | 32.41 | 32.80 | 32.08 |
| Wall TPS overhead | 41.67% | 45.47% | 44.81% | 45.53% |
| TTFT delta | 31.07 ms | 32.09 ms | 33.72 ms | 38.08 ms |
| Total latency delta | 725.72 ms | 933.50 ms | 912.69 ms | 941.51 ms |
| Active-KV decode model avg | 8910 us | 9814 us | 9740 us | 9809 us |
| Active-KV decode quantize avg | 0 us | 0 us | 0 us | 0 us |
| Active-KV memory savings | 75% | 75% | 75% | 75% |
| Kernel path | affine quantized SDPA | affine quantized SDPA | fallback | fallback |
| Runtime route | N/A | N/A | blocked | blocked |
| Runtime block reason | N/A | N/A | attention hook unavailable | attention hook unavailable |
| Candidate dispatch count, 5 runs | N/A | N/A | 0 | 5 |
| Per-run fallback count | 0 | 0 | 1 | 1 |
| Release-gate fallback count, 5 runs | 0 | 0 | 5 | 5 |

The per-run q4 `active_kv_decode_quantize_total_us` values changed from
`[23, 32, 21, 33, 28]` to `[0, 0, 0, 0, 0]`. The same post-run values are zero
for `decode_turboquant_q4`.
The fused TurboQuant release gate still intentionally fails on both current
post-runs. The default speedup post-run reports `status = "fail"`,
`candidate_dispatch_count = 0`, `fallback_count = 5`, and
`worker_tps_overhead_pct = 45.76`. The explicit probe-mode candidate post-run
reports `status = "fail"`, `candidate_dispatch_count = 5`,
`fallback_count = 5`, `observed_kernel_paths = ["fallback"]`,
`observed_runtime_routes = ["blocked"]`,
`observed_runtime_block_reasons = ["attention_hook_unavailable"]`, and
`worker_tps_overhead_pct = 44.83`. This preserves candidate-dispatch evidence
without treating it as runtime success.

Interpretation: the guard did remove the redundant maintenance work, but that
work was already too small to move end-to-end throughput. The remaining overhead
is in the quantized attention model call, not the Melix decode loop wrapper.

## Next Optimization Architecture

The next real TurboQuant optimization must replace the current fallback profile
with a fused decode implementation. The recommended order is:

1. Add an explicit capability gate.
   Keep `turboquant-q4` mapped to `fallback` unless a fused cache implementation
   is actually active. Metrics should fail the release gate if a TurboQuant
   profile reports `active_kv_kernel_path = fallback`. This gate now exists as
   `swift_worker_direct.active_kv_release_gates.turboquant_fused_decode` and the
   `--require-fused-turboquant` CLI flag.

2. Prove custom Metal feasibility in Swift.
   The pinned Swift MLX checkout exposes `MLXFast.metalKernel(...)` and
   `MLXFastKernel.callAsFunction(...)`, which is the required custom Metal
   dispatch surface. The text worker target now has the `MLXFast` product
   dependency, a runtime smoke test that dispatches an identity custom kernel,
   and an isolated MSE q4 value decode plus attention-weight accumulation
   kernel, and an isolated MSE q4 score plus softmax plus value kernel. The
   next implementation should turn this proof into a feature-gated cache path
   with release-gated metrics before changing the default active runtime path.

3. Implement a Swift `TurboQuantKVCacheProtocol` path.
   It should store packed quantized key/value state, preserve offset and state
   serialization semantics, and use deterministic codecs from bit width plus seed.
   Single-token decode should use fused key+value quantization for appends where
   supported.

4. Route only single-token decode to fused attention.
   Match oMLX: if query length is one and the cache is TurboQuant, call fused
   decode attention. For prefill, use normal attention or a quantized prefill
   fast path only when it has separate probe evidence.

5. Add fused score plus softmax plus value kernels.
   The release target is a kernel path equivalent to MLX-VLM's fully fused or MSE
   fused decode path, not the current affine quantized SDPA. The first milestone
   can be MSE q4 only, because it matches the frozen affine q4 baseline.

6. Add batch operations after single-request decode is stable.
   Continuous batching should mirror oMLX by subclassing or otherwise sharing
   the single-request decode logic. Batch-specific code should only own
   merge/extract/extend/filter and per-request left padding.

## Measurement Gates

Do not claim TurboQuant optimization success without a post-run JSON produced by
the same `scripts/phase2_metrics_report.py` command family and the same real
model class.

Release-gate targets:

- `swift_worker_direct.active_kv_release_gates.turboquant_fused_decode.status = "pass"`
- `swift_worker_direct.active_kv_fused_candidate_probes.turboquant_q4.status = "runtime_candidate_pass"` as supporting evidence; it does not replace the release gate
- `active_kv_kernel_path` is not `fallback` for `decode_turboquant_q4`
- `active_kv_fallback_count = 0`
- `active_kv_decode_quantize_total_us = 0` for already-quantized decode
- `active_kv_estimated_memory_savings_pct >= 67`
- `worker_tps_overhead_pct <= 15` for the first fused milestone
- `worker_tps_overhead_pct <= 10` for oMLX parity

Quality and correctness gates:

- active-KV decode emits a non-empty completion for the live Swift bridge tests
- baseline-prefill plus active-KV decode can lazily quantize once and then stop
  repeated maintenance attempts
- Phase 2 report includes baseline, affine q4, and TurboQuant rows in one file
- any future `BatchTurboQuantKVCache` equivalent has merge, extract, extend,
  filter, and left-padding tests before scheduler integration
