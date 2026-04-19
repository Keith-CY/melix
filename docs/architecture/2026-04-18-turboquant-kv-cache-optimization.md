# TurboQuant KV Cache Optimization

## Context

Melix active-KV quantization is opt-in and currently stores KV state through
Swift MLX LM's `QuantizedKVCache` path. That path gives measurable KV memory
reduction, and the vendored runtime now routes supported one-token affine-q4
decode through a fused Metal dispatch. It is still not the full oMLX
TurboQuant cache architecture.

The current benchmark evidence is:

| Evidence | File | Model | Profiles |
| --- | --- | --- | --- |
| Pre-optimization baseline | `docs/metrics/phase2-affine-q4-preopt.json` | `mlx-community/Qwen3-0.6B-4bit` | `q4` |
| Decode-guard post-optimization | `docs/metrics/phase2-active-kv-decode-guard-postopt.json` | `mlx-community/Qwen3-0.6B-4bit` | `q4`, `turboquant-q4` |
| Runtime speedup post-optimization | `docs/metrics/phase2-active-kv-runtime-speedup-postopt.json` | `mlx-community/Qwen3-0.6B-4bit` | `q4`, `turboquant-q4` |
| Fused TurboQuant candidate audit | `docs/metrics/phase2-active-kv-fused-turboquant-candidate.json` | `mlx-community/Qwen3-0.6B-4bit` | `q4`, `turboquant-q4` |
| Terminal model-call pre-optimization probe | `docs/metrics/phase2-active-kv-terminal-model-call-preopt.json` | `mlx-community/Qwen3-0.6B-4bit` | `q4`, `turboquant-q4` |
| Terminal model-call post-optimization probe | `docs/metrics/phase2-active-kv-terminal-model-call-postopt.json` | `mlx-community/Qwen3-0.6B-4bit` | `q4`, `turboquant-q4` |
| Lazy-eval timing probe | `docs/metrics/phase2-active-kv-lazy-eval-probe.json` | `mlx-community/Qwen3-0.6B-4bit` | `q4`, `turboquant-q4` |
| Blocked fallback speedup post-optimization | `docs/metrics/phase2-active-kv-blocked-fallback-speedup-postopt.json` | `mlx-community/Qwen3-0.6B-4bit` | `q4`, `turboquant-q4` |
| Vendored TurboQuant runtime probe | `docs/metrics/phase2-active-kv-vendored-turboquant-runtime.json` | `mlx-community/Qwen3-0.6B-4bit` | `turboquant-q4` |
| Vendored shared-score speedup probe | `docs/metrics/phase2-active-kv-vendored-turboquant-shared-scores.json` | `mlx-community/Qwen3-0.6B-4bit` | `turboquant-q4` |
| Vendored online-softmax speedup probe | `docs/metrics/phase2-active-kv-vendored-turboquant-online-softmax.json` | `mlx-community/Qwen3-0.6B-4bit` | `turboquant-q4` |
| Cache-internal timing probe | `docs/metrics/phase2-active-kv-vendored-turboquant-cache-probe.json` | `mlx-community/Qwen3-0.6B-4bit` | `turboquant-q4` |
| Vendored storage-fastpath speedup probe | `docs/metrics/phase2-active-kv-vendored-turboquant-storage-fastpath.json` | `mlx-community/Qwen3-0.6B-4bit` | `turboquant-q4` |
| Rejected fused decode-quantize experiment | `docs/metrics/phase2-active-kv-vendored-turboquant-fused-quantize-experiment.json` | `mlx-community/Qwen3-0.6B-4bit` | `turboquant-q4` |
| Vendored append-slice speedup probe | `docs/metrics/phase2-active-kv-vendored-turboquant-append-slice.json` | `mlx-community/Qwen3-0.6B-4bit` | `turboquant-q4` |
| Qwen3.5 support smoke | `docs/metrics/phase2-active-kv-qwen35-support-smoke.json` | `mlx-community/Qwen3.5-0.8B-OptiQ-4bit` | `turboquant-q4` |
| Fused eval-sync probe | `docs/metrics/phase2-active-kv-vendored-turboquant-eval-probe.json` | `mlx-community/Qwen3.5-0.8B-OptiQ-4bit` | `turboquant-q4` |
| Qwen3.5 hybrid-cache routed probe | `docs/metrics/phase2-active-kv-qwen35-hybrid-turboquant-routing.json` | `mlx-community/Qwen3.5-0.8B-OptiQ-4bit` | `turboquant-q4` |
| Qwen3.5 hybrid-cache stability summary | `docs/metrics/phase2-active-kv-qwen35-hybrid-stability-summary.json` | `mlx-community/Qwen3.5-0.8B-OptiQ-4bit` | `turboquant-q4` |
| Qwen3.5 TurboQuant speedup pre-optimization | `docs/metrics/phase2-active-kv-qwen35-turboquant-speedup-preopt.json` | `mlx-community/Qwen3.5-0.8B-OptiQ-4bit` | `turboquant-q4` |
| Qwen3.5 TurboQuant speedup post-optimization | `docs/metrics/phase2-active-kv-qwen35-turboquant-speedup-postopt.json` | `mlx-community/Qwen3.5-0.8B-OptiQ-4bit` | `turboquant-q4` |
| Qwen3.5 TurboQuant speedup stability summary | `docs/metrics/phase2-active-kv-qwen35-turboquant-speedup-stability-summary.json` | `mlx-community/Qwen3.5-0.8B-OptiQ-4bit` | `turboquant-q4` |

`mlx-community/Qwen3.5-0.8B-OptiQ-4bit` remains the shared Phase 8 real-model
E2E convention. Melix now vendors Qwen3.5 model support from
`mlx-swift-lm` 2.31.3, so the real Qwen3.5 stack can load and decode. Active-KV
fused routing now handles Qwen3.5's hybrid cache by leaving Mamba cache entries
unchanged and quantizing supported full-attention `KVCacheSimple` entries. The
Qwen3.5 hybrid-cache routed probe is the current fused release-gate pass
evidence.

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

## Current Melix State

Melix exposes a `turboquant-q4` profile for probes. Before the vendored runtime
patch, the profile used Swift MLX LM affine `QuantizedKVCache` through upstream
quantized attention. The historical post-optimization probe correctly reported:

- `decode_affine_q4`: backend `affine`, kernel path `affine_quantized_sdpa`
- `decode_turboquant_q4`: backend `turboquant`, kernel path `fallback`, with
  `active_kv_fallback_count = 1`

That meant the profile was observable, but not backed by a fused TurboQuant
runtime path. The vendored-runtime slice changes that routing state:

- `decode_turboquant_q4` now reports `active_kv_kernel_path = "tq_mse_single"`
- `active_kv_runtime_route = "routed"`
- `active_kv_fallback_count = 0`
- `active_kv_decode_quantize_total_us = 0`
- `active_kv_estimated_memory_savings_pct = 75`

The remaining gap is performance, not route availability. The first real-model
vendored JSON reports `worker_tps_overhead_pct = 68.63`. A follow-up
shared-score kernel layout reduces that to `60.87`, but the fused TurboQuant
release gate remains failed because the required threshold is `<= 15`.
The online-softmax follow-up keeps the non-fallback route and removes the
threadgroup score-vector materialization, but its real-model JSON still reports
`worker_tps_overhead_pct = 60.0`, so the release gate remains failed.
The cache-storage follow-ups remove trimmed-state materialization and slightly
reduce append indexing overhead, but the latest routed JSON still reports
`worker_tps_overhead_pct = 60.0`. The fused decode-quantize experiment is
correctness-covered, including bfloat16, but is disabled by default because it
regressed real-model `cache_quantize_total_us`.

The fused eval-sync probe adds per-cache fused attention timing counters and an
opt-in `MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE=1` model evaluation sync
timer. On the shared Qwen3.5 real-model convention, the probe keeps the release
gate failed: `active_kv_kernel_path = "fallback"`,
`active_kv_runtime_route = "blocked"`,
`active_kv_runtime_block_reason = "unsupported_cache_state"`,
`active_kv_fallback_count = 3`, and
`active_kv_estimated_memory_savings_pct = 0.0`. It reports
`decode_model_eval_sync_total_us = 4311359` over `189` calls, comparison median
`active_kv_decode_model_eval_sync_avg_us = 22607`, and fused attention call
count zero, confirming this Qwen3.5 run never entered the vendored fused
attention route.

The hybrid-cache routing fix changes dynamic KV quantization from a leading
cache-entry guard to per-layer scanning. Qwen3.5 starts with `MambaCache`
entries for linear-attention layers and uses `KVCacheSimple` entries for
full-attention layers. Melix now skips the Mamba entries, quantizes eligible
full-attention entries, and lets the vendored q4 attention route run on those
quantized states. The real Qwen3.5 routed JSON reports release gate `status =
"pass"`, `active_kv_kernel_path = "tq_mse_single"`,
`active_kv_runtime_route = "routed"`, `active_kv_fallback_count = 0`,
`active_kv_estimated_memory_savings_pct = 75.0`,
`fused_attention_call_count = 1134`, and
`worker_tps_overhead_pct = 12.82`, so it satisfies the first fused milestone's
`<= 15` worker overhead threshold.

The follow-up Qwen3.5 hybrid-cache stability summary records five sequential
real-model runs against the same routed profile. All five runs pass the explicit
fused release gate, keep `active_kv_kernel_path = "tq_mse_single"`, keep
`active_kv_runtime_route = "routed"`, keep `active_kv_fallback_count = 0`, and
report `worker_tps_overhead_pct` min/median/mean/max of
`5.71 / 10.26 / 9.722 / 12.82`.

The Qwen3.5 TurboQuant speedup slice adds fused-attention launch and softmax
lane probes before changing the kernel. The pre-optimization JSON disproves the
launch-width hypothesis for Qwen3.5: active lanes and launched lanes are both
`12096`, so inactive lane count is `0`. The optimization therefore keeps the
same 32-lane launch shape and removes duplicated per-token work inside the
active lanes: online softmax is computed on lane 0 and broadcast to value lanes,
and each lane's eight query values are hoisted out of the historical-token loop.
The post-optimization JSON keeps `active_kv_kernel_path = "tq_mse_single"`,
`active_kv_runtime_route = "routed"`, and `active_kv_fallback_count = 0`, while
reducing softmax token-lane work from `641088` to `20034` and reporting
`worker_tps_overhead_pct = 5.13`. The TPS delta is single-run evidence and
should be treated as noisy; the softmax token-lane reduction is the deterministic
work-reduction evidence.

The follow-up Qwen3.5 TurboQuant speedup stability summary uses the same
`MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE=1` timing mode as the speedup
JSONs and records a warmup-aware protocol: one warmup run is preserved but
excluded from the five measured runs. All five measured runs pass the explicit
fused release gate, stay non-fallback, stay routed, and keep
`active_kv_fallback_count = 0`. `worker_tps_overhead_pct`
min/median/mean/max is `10.0 / 10.26 / 11.044 / 12.5`, so the speedup has
repeated-run release-gate evidence under the warmup protocol. The summary is
generated by the Phase 2 metrics stability mode with
`--stability-warmup-count 1`, `--stability-required-runs 5`, and
`--require-fused-turboquant`; the warmup run is recorded only as cold-start
context.

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

The first fused attention smoke kernel intentionally favored capability and
correctness over the final parallel layout, so it removed uncertainty around
whether the Swift package can host custom Metal kernels for packed-q4 score,
softmax, and value work without claiming an optimized runtime path.

The second runtime-candidate slice keeps
`active_kv_candidate_dispatch_code = 1` as "a candidate dispatch ran", but now
prefers a live `QuantizedKVCache` state over the fixed smoke arrays. The
candidate helper slices the first batch/head from MLXLM's affine q4 cache tuple
and decodes MLX's `uint32` bit-packed q4 layout in one Metal dispatch for
score, softmax, and value. If no supported cache state is available, the decode
probe falls back to the original fixed smoke arrays.

The runtime route decision is explicit and is separate from candidate dispatch.
Melix now vendors `mlx-swift-lm` under `third_party/mlx-swift-lm` at upstream
commit `5064b8c5d8ed3b0bbb71385c4124f0fc102e74a2`, patches
`MLXLMCommon.attentionWithCacheUpdate(...)`, and tries
`fusedQ4ScaledDotProductAttention(...)` before the upstream affine q4 quantized
SDPA fallback. The fused route supports one-token decode for MLX's affine q4
`QuantizedKVCache` layout and handles grouped-query attention by mapping query
heads to KV heads inside one Metal dispatch.

The route is promoted only after model attention actually dispatches the fused
kernel. `QuantizedKVCache` records a per-cache fused attention dispatch count,
and Melix exports `active_kv_runtime_route`,
`active_kv_runtime_block_reason`, `active_kv_kernel_path`, and
`active_kv_fallback_count` from that evidence. Candidate smoke dispatch alone
does not set `active_kv_kernel_path` to fused.

The runtime no longer requires `MELIX_SWIFT_TURBOQUANT_CANDIDATE_PROBE=1` to
enable the vendored route. That environment flag now controls only the
supporting candidate/smoke dispatch path used for audits.

Unsupported runtime states still fall back. The vendored helper returns nil for
non-affine, non-q4, non-decode, or array-mask attention shapes, then the
existing upstream quantized attention path runs. The custom Metal kernel is
scoped to the GPU stream for the fused op so CPU-hosted test/model execution can
still exercise the route without switching the entire model graph to GPU.

The default runtime keeps candidate dispatch disabled.
`active_kv_candidate_eligibility_check_count` measures supporting candidate
probe work in the decode loop; the current optimized default path precomputes
whether a candidate probe can run and reports zero checks unless
`MELIX_SWIFT_TURBOQUANT_CANDIDATE_PROBE=1` is set before worker startup.

The vendored runtime has now produced a real-model JSON with a non-fallback
kernel path, but the release gate remains blocked until the same JSON also
shows `worker_tps_overhead_pct <= 15`.

The first runtime-speedup slice removed the candidate dispatch from the default
pre-vendored blocked route. `MELIX_SWIFT_TURBOQUANT_CANDIDATE_PROBE=1` explicitly
opts into the live fused-candidate probe. `scripts/dev_up.py` passes the probe
flag through to the Swift worker and writes it into `env.sh` only when the
parent environment sets it, so normal runtime paths stay measurement-clean
while candidate-audit runs remain reproducible.

That was a small runtime cleanup, not the real TurboQuant decode architecture.
The default real-model run from that stage confirmed candidate dispatch count
dropped from five to zero, but the worker throughput overhead remained 45.76
percent because the dependency-owned quantized attention model call was still
the hot path.

The second runtime-speedup slice adds `active_kv_decode_model_call_count` and
stops prepared decode before a terminal next-token model call once
`maxOutputTokens` has already been emitted. This removes one unused model call
per 64-token active-KV decode run in the historical fallback benchmark shape.
That real-model probe kept the release gate blocked because the TurboQuant
kernel path was still `fallback` and worker throughput overhead was still above
15 percent.

The lazy-eval timing probe adds `active_kv_decode_token_eval_*` and
`active_kv_decode_loop_total_us`. Swift MLX model calls build lazy graphs, so
`active_kv_decode_model_*` measures graph construction but not the full GPU
execution forced by sampling and `token.item(Int.self)`. The probe shows the
remaining time is dominated by token evaluation, which is where the dependency
owned quantized attention path executes.

The blocked-fallback speedup was the last pre-vendored guard: it prevented
default `turboquant-q4` from silently using affine q4 cache while the attention
hook was unavailable. The vendored route supersedes that blocked default by
running fused affine q4 decode when `attentionWithCacheUpdate(...)` sees a
supported decode cache. Explicit `q4` still provides affine KV compression, and
candidate audits can still set `MELIX_SWIFT_TURBOQUANT_CANDIDATE_PROBE=1` to
exercise the smoke/candidate path. A compatibility opt-in,
`MELIX_SWIFT_TURBOQUANT_AFFINE_FALLBACK=1`, remains available for developer
probes.

## Before And After Metrics

The historical pre-vendored runs used:

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

Terminal model-call cleanup evidence:

| Metric | Pre terminal-call cleanup | Post terminal-call cleanup |
| --- | ---: | ---: |
| TurboQuant decode model calls, 5 runs | 320 | 315 |
| TurboQuant per-run decode model calls | 64 | 63 |
| Affine q4 decode model calls, 5 runs | 320 | 315 |
| Affine q4 per-run decode model calls | 64 | 63 |
| Baseline worker decode tok/s | 61.0 | 62.0 |
| TurboQuant worker decode tok/s | 35.0 | 35.0 |
| TurboQuant worker TPS overhead | 42.62% | 43.55% |
| TurboQuant wall TPS overhead | 42.97% | 43.45% |
| TurboQuant active-KV decode model avg | 9597 us | 9523 us |
| TurboQuant kernel path | fallback | fallback |
| TurboQuant release gate | fail | fail |

Lazy-eval timing evidence:

| Metric | TurboQuant fallback |
| --- | ---: |
| Baseline worker decode tok/s | 59.0 |
| TurboQuant worker decode tok/s | 34.0 |
| TurboQuant worker TPS overhead | 42.37% |
| TurboQuant decode loop total, 5 runs | 9,497,000 us |
| TurboQuant decode token eval total, 5 runs | 6,438,631 us |
| TurboQuant decode model construction total, 5 runs | 3,018,404 us |
| TurboQuant median token eval avg | 19,945 us |
| TurboQuant median model construction avg | 9,303 us |
| TurboQuant kernel path | fallback |
| TurboQuant release gate | fail |

Blocked fallback speedup evidence:

| Metric | Lazy-eval fallback | Blocked fallback speedup |
| --- | ---: | ---: |
| Baseline worker decode tok/s | 59.0 | 59.0 |
| TurboQuant worker decode tok/s | 34.0 | 61.0 |
| TurboQuant worker TPS overhead | 42.37% | -3.39% |
| TurboQuant wall TPS overhead | 42.31% | -1.64% |
| TurboQuant decode loop total, 5 runs | 9,497,000 us | 5,473,976 us |
| TurboQuant decode token eval total, 5 runs | 6,438,631 us | 4,009,440 us |
| TurboQuant median token eval avg | 19,945 us | 11,987 us |
| TurboQuant median model construction avg | 9,303 us | 4,387 us |
| TurboQuant memory savings | 75% | 0% |
| TurboQuant quantization ratio | 25% | 0% |
| TurboQuant kernel path | fallback | fallback |
| TurboQuant runtime route | blocked | blocked |
| TurboQuant block reason | attention hook unavailable | attention hook unavailable |
| TurboQuant release gate | fail | fail |

Vendored runtime evidence:

| Metric | Vendored runtime |
| --- | ---: |
| Decode repeats | 3 |
| Baseline worker decode tok/s | 51.0 |
| TurboQuant worker decode tok/s | 16.0 |
| TurboQuant worker TPS overhead | 68.63% |
| TurboQuant wall TPS overhead | 69.47% |
| TurboQuant decode loop total, 3 runs | 19,315,210 us |
| TurboQuant decode token eval total, 3 runs | 15,894,621 us |
| TurboQuant median token eval avg | 45,268 us |
| TurboQuant median model construction avg | 18,761 us |
| TurboQuant memory savings | 75% |
| TurboQuant quantization ratio | 25% |
| TurboQuant candidate dispatch count | 0 |
| TurboQuant fallback count | 0 |
| TurboQuant kernel path | tq_mse_single |
| TurboQuant runtime route | routed |
| TurboQuant release gate | fail |

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
The blocked-fallback post-run reports `status = "fail"`,
`candidate_dispatch_count = 0`, `fallback_count = 5`,
`observed_runtime_routes = ["blocked"]`,
`observed_runtime_block_reasons = ["attention_hook_unavailable"]`,
`worker_tps_overhead_pct = -3.39`, and
`active_kv_estimated_memory_savings_pct = 0.0`.
The vendored runtime post-run reports `status = "fail"`,
`candidate_dispatch_count = 0`, `fallback_count = 0`,
`observed_kernel_paths = ["tq_mse_single"]`,
`observed_runtime_routes = ["routed"]`,
`active_kv_estimated_memory_savings_pct = 75.0`, and
`worker_tps_overhead_pct = 68.63`. This proves runtime routing without
unblocking the release gate.
The shared-score speedup post-run keeps the same non-fallback runtime state and
reports `candidate_dispatch_count = 0`, `fallback_count = 0`,
`observed_kernel_paths = ["tq_mse_single"]`,
`observed_runtime_routes = ["routed"]`,
`active_kv_estimated_memory_savings_pct = 75.0`, and
`worker_tps_overhead_pct = 60.87`. This improves the vendored route by 7.76
percentage points but still does not unblock the release gate.
The online-softmax post-run keeps `candidate_dispatch_count = 0`,
`fallback_count = 0`, `observed_kernel_paths = ["tq_mse_single"]`,
`observed_runtime_routes = ["routed"]`,
`active_kv_decode_quantize_total_us = 0`,
`active_kv_decode_token_eval_total_us = 6601404`,
`active_kv_estimated_memory_savings_pct = 75.0`, and
`worker_tps_overhead_pct = 60.0`. This confirms the single-simdgroup online
softmax route executes, but it still does not unblock the release gate.
The packed-word-lane post-run keeps the same non-fallback runtime evidence and
reports `candidate_dispatch_count = 0`, `fallback_count = 0`,
`observed_kernel_paths = ["tq_mse_single"]`,
`observed_runtime_routes = ["routed"]`,
`active_kv_decode_quantize_total_us = 0`,
`active_kv_decode_token_eval_total_us = 2554186`,
`active_kv_estimated_memory_savings_pct = 75.0`, and
`worker_tps_overhead_pct = 73.97`. It improves absolute TurboQuant decode token
evaluation from 6,601,404 us to 2,554,186 us versus the online-softmax run, but
the same-run baseline was much faster, so the release gate remains failed.
The cache-internal timing probe keeps the same non-fallback runtime evidence and
adds per-cache breakdown. Across three 64-token `turboquant-q4` decode repeats
it reports `cache_update_total_us = 1081676`,
`cache_update_call_count = 5376`, `cache_append_total_us = 621474`,
`cache_quantize_total_us = 93119`,
`cache_materialize_total_us = 348621`,
`cache_materialize_call_count = 5379`, median
`active_kv_cache_update_avg_us = 200.0`, and median
`active_kv_cache_materialize_avg_us = 64.0`. The routed fused path remains
release-blocked because `worker_tps_overhead_pct = 73.61`.
The storage-fastpath post-run keeps the routed non-fallback evidence and removes
decode-side trimmed-state materialization from the fused attention path. It
reports `cache_update_total_us = 728859`,
`cache_update_call_count = 5376`, `cache_append_total_us = 615953`,
`cache_quantize_total_us = 92171`,
`cache_materialize_total_us = 278`,
`cache_materialize_call_count = 3`, median
`active_kv_cache_update_avg_us = 135.0`, and median
`active_kv_cache_materialize_avg_us = 93.0`. That confirms the storage path is
active, but the routed fused path remains release-blocked because
`worker_tps_overhead_pct = 61.43`.
The fused decode-quantize experiment validates a single-dispatch q4 affine
key/value quantizer, fixes bfloat16 scale/bias output casting, and keeps
`active_kv_kernel_path = tq_mse_single`, `active_kv_runtime_route = routed`,
and `active_kv_fallback_count = 0`. The real-model data rejects it as a default
runtime optimization: aggregate `cache_quantize_total_us` regresses from the
storage-fastpath `92171` us to `823275` us, and `cache_update_total_us`
regresses to `1575930` us. It remains available only behind
`MELIX_SWIFT_TURBOQUANT_FUSED_QUANTIZE=1` for future experiments.
The append-slice post-run keeps native MLX quantization as the default and
shortens q4 storage writes to direct 3-axis slice updates. It reports
`cache_update_total_us = 725794`,
`cache_update_call_count = 5376`, `cache_append_total_us = 592356`,
`cache_quantize_total_us = 112194`, `cache_materialize_total_us = 304`, and
`cache_materialize_call_count = 3`. This improves aggregate append time by
`23597` us versus the storage-fastpath run, but the routed fused path remains
release-blocked because `worker_tps_overhead_pct = 60.0`.

Interpretation: the guard did remove the redundant maintenance work, and the
terminal-call cleanup removed one unused model step per decode run, but both are
too small to move end-to-end throughput. The lazy-eval probe shows about 68
percent of the TurboQuant fallback decode loop is spent in token evaluation,
where Swift MLX executes the dependency-owned quantized attention graph. That
keeps affine-q4 fallback below the release target. The blocked-fallback speedup
removes that user-visible overhead for default `turboquant-q4`, but it is not a
TurboQuant success: it trades away KV compression while the runtime hook remains
blocked, so the fused release gate must remain failed. The vendored runtime
restores KV compression and removes fallback, but the first fused kernel is still
slower than the release target.

Implementation inference: the first Swift fused kernel dispatched one output
element per thread and recomputed the key score plus softmax pass for every
output dimension. The shared-score follow-up now launches one threadgroup per
batch/query-head, reduces key scores across head-dimension lanes with simdgroup
partial reductions, stores one score vector in threadgroup memory, and shares
per-token softmax weights across value lanes. That removes the largest repeated
score pass. The online-softmax follow-up removes the materialized score vector
and uses one simdgroup per batch/query-head so each value lane rescales its
accumulator as scores arrive. The packed-word-lane follow-up maps each active
lane to one q4 `uint32` word and accumulates eight output dimensions from that
packed load. The storage-fastpath follow-up lets fused decode consume
preallocated q4 cache storage with an explicit valid sequence length, so
`updateQuantizedStorage(...)` no longer slices a trimmed state for every token.
The absolute TurboQuant path is faster, but the real-model data shows the route
is still too slow for the release target, so the next optimization must address
remaining per-token fused-kernel evaluation, cache append, and incoming KV
quantization overhead.
The fused decode-quantize experiment shows that a naive custom quantizer is not
the right next default step: MLX's native `quantized(...)` implementation is
substantially faster than the single-thread-per-group custom kernel on the live
decode shape. Future quantization work should either write directly into cache
storage with a parallel layout or leave native quantization in place.

The cache-internal timing probe now separates the remaining runtime cost inside
Swift MLX LM's `QuantizedKVCache`. Each active-KV decode row can include:

- `active_kv_cache_update_total_us`, `active_kv_cache_update_call_count`, and
  `active_kv_cache_update_avg_us`
- `active_kv_cache_expand_total_us` for storage initialization or growth
- `active_kv_cache_quantize_total_us` for incoming key/value tensor
  quantization
- `active_kv_cache_append_total_us` for writing packed key/value tuples into
  cache storage
- `active_kv_cache_materialize_total_us`,
  `active_kv_cache_materialize_call_count`, and
  `active_kv_cache_materialize_avg_us` for trimmed quantized state returned by
  `updateQuantized(...)` or read through `getQuantizedState()`

The phase 2 report propagates those fields into decode comparisons, release-gate
runtime evidence, and fused-candidate runtime evidence. They do not change the
release rule: a real-model JSON must still show `active_kv_kernel_path !=
fallback` and `worker_tps_overhead_pct <= 15` in the same run before the fused
TurboQuant gate can pass.

## Next Optimization Architecture

The next real TurboQuant optimization must speed up the vendored fused route.
Routing is now proven; the remaining work is kernel layout and dispatch
efficiency. The recommended order is:

1. Add an explicit capability gate.
   Keep `turboquant-q4` mapped to `fallback` unless a fused cache implementation
   is actually active. Metrics should fail the release gate if a TurboQuant
   profile reports `active_kv_kernel_path = fallback`. This gate now exists as
   `swift_worker_direct.active_kv_release_gates.turboquant_fused_decode` and the
   `--require-fused-turboquant` CLI flag.

2. Optimize the vendored fused kernel layout.
   The current packed-word-lane kernel is a route-plus-layout proof. It goes
   beyond the online-softmax vector lane layout by dequantizing one q4 `uint32`
   word per active lane and accumulating eight value dimensions from that load,
   and the storage-fastpath slice removes per-token trimmed-cache
   materialization from the fused route. The append-slice cleanup slightly
   reduces cache append overhead, while the fused decode-quantize experiment is
   rejected for default runtime use because it is slower than native MLX
   quantization. The latest same-model gate still fails at
   `worker_tps_overhead_pct = 60.0`. The next kernel slice should reduce
   remaining per-token fused-kernel evaluation before rerunning the release
   gate.

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
model class. The current Qwen3.5 hybrid-cache routed JSON is valid fused-release
evidence because it reports a non-fallback kernel path and worker overhead below
the first fused milestone threshold. Older Qwen3.5 support-smoke and eval-sync
JSON files remain historical blocked evidence and should not be used as pass
evidence. The Qwen3.5 hybrid-cache stability summary adds repeated-run evidence:
5/5 runs pass the same gate, with maximum `worker_tps_overhead_pct = 12.82`.

Release-gate targets:

- `swift_worker_direct.active_kv_release_gates.turboquant_fused_decode.status = "pass"`
- `swift_worker_direct.active_kv_fused_candidate_probes.turboquant_q4.status = "runtime_candidate_pass"` as supporting evidence; it does not replace the release gate
- `active_kv_kernel_path` is not `fallback` for `decode_turboquant_q4`
- `active_kv_fallback_count = 0`
- `active_kv_decode_quantize_total_us = 0` for already-quantized decode
- `active_kv_estimated_memory_savings_pct >= 67`
- `worker_tps_overhead_pct <= 15` for the first fused milestone
- `worker_tps_overhead_pct <= 10` for oMLX parity

The packed-word-lane probe does not change the release rule: the gate remains
blocked unless the same real-model JSON reports both `active_kv_kernel_path !=
fallback` and `worker_tps_overhead_pct <= 15`. The current packed-word-lane JSON
meets the non-fallback requirement but fails the throughput requirement with
`worker_tps_overhead_pct = 73.97`.
The storage-fastpath probe also does not change the release rule: it drops
aggregate trimmed-state materialization from `348621` us to `278` us and keeps
`active_kv_kernel_path = tq_mse_single`, but the same-model JSON still fails the
throughput requirement with `worker_tps_overhead_pct = 61.43`.
The append-slice probe also does not change the release rule: it lowers
aggregate append timing from `615953` us to `592356` us and keeps
`active_kv_kernel_path = tq_mse_single`, but the same-model JSON still fails the
throughput requirement with `worker_tps_overhead_pct = 60.0`.
The fused decode-quantize experiment must remain opt-in: it validates bfloat16
correctness but regresses aggregate quantization timing to `823275` us, so it is
not release-gate evidence.
The Qwen3.5 support smoke also keeps the release gate blocked: it proves the
Swift stack can load and decode `model_type = qwen3_5`, but `turboquant-q4`
reports `active_kv_kernel_path = fallback`, `active_kv_runtime_route = blocked`,
`active_kv_runtime_block_reason = unsupported_cache_state`,
`active_kv_fallback_count = 1`, and `active_kv_estimated_memory_savings_pct = 0.0`.
The Qwen3.5 hybrid-cache routed probe supersedes that blocked evidence for the
release gate: it reports `active_kv_kernel_path = tq_mse_single`,
`active_kv_runtime_route = routed`, `active_kv_fallback_count = 0`,
`active_kv_estimated_memory_savings_pct = 75.0`, and
`worker_tps_overhead_pct = 12.82`.
The stability summary preserves repeated-run evidence for the same model and
profile: 5/5 release-gate passes, `active_kv_fallback_count = 0` in every run,
and maximum `worker_tps_overhead_pct = 12.82`.
The Qwen3.5 TurboQuant speedup post-optimization JSON is a same-model
single-run pass after the kernel work reduction. It keeps the release-gate route
non-fallback and routed, reduces softmax token-lane work from `641088` to
`20034`, and reports `worker_tps_overhead_pct = 5.13`. The matching
pre-optimization JSON is useful for lane-probe comparison but is not pass
evidence because that single run reports `worker_tps_overhead_pct = 17.5`.
The speedup stability summary records one warmup run followed by five measured
runs. The measured runs report `pass_count = 5`, `run_count = 5`, and maximum
`worker_tps_overhead_pct = 12.5`, while all measured runs stay non-fallback,
routed, and `active_kv_fallback_count = 0`. The release evidence is produced by
`scripts/phase2_metrics_report.py` with `--stability-input-json`,
`--stability-warmup-count 1`, `--stability-required-runs 5`, and
`--require-fused-turboquant`, so stability gate checks use the same non-fallback
and worker-overhead rules as single-run Phase 2 reports.

Quality and correctness gates:

- active-KV decode emits a non-empty completion for the live Swift bridge tests
- baseline-prefill plus active-KV decode can lazily quantize once and then stop
  repeated maintenance attempts
- Phase 2 report includes baseline, affine q4, and TurboQuant rows in one file
- any future `BatchTurboQuantKVCache` equivalent has merge, extract, extend,
  filter, and left-padding tests before scheduler integration
