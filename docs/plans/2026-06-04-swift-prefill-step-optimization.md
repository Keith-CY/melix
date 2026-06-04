# Swift Text Prefill Step Optimization Plan

## Context

The June 4, 2026 128k serving comparison showed Melix TTFT dominated by Swift
text worker prefill rather than gateway or scheduler overhead:

- Client TTFT p50 was about 34.1 seconds.
- `swift_text.prefill_ms` was about 33.7 seconds.
- `swift_text.decode_ttft_ms` was about 0.57 seconds.
- Gateway shaping and route resolution were sub-millisecond, and scheduler
  admission/queue delay was about 27 ms.

The scheduler progress chunk target and the worker model prefill step are
separate values. `scheduler.prefill_chunk_target_tokens=16` is progress
accounting; the Swift text worker receives `prefillStepSize` and uses it as the
MLXLMCommon prompt prepare step. Before this plan, all non-vision text requests
used a fixed worker prefill step of 512 tokens.

## Goal

Reduce long-context text TTFT by widening the Swift text worker prefill step for
large text-only prompts while preserving the existing short-prompt and vision
paths.

## Scope

- Keep text-only prompts below 32k estimated tokens on the existing 512-token
  worker prefill step.
- Use a 1024-token worker prefill step for text-only prompts at or above 32k
  estimated tokens.
- Preserve the 16-token scheduler progress chunk target and progress metrics.
- Preserve the vision-bearing request path, which uses boundary-safe progress
  chunks rather than the text worker window.
- Verify with focused control-plane tests and a real 128k Gemma E4B serving
  benchmark before making a performance claim.

Out of scope:

- Changing MLXLMCommon or vendored Gemma4 cache semantics.
- Changing scheduler progress event granularity.
- Changing acceleration profile selection.
- Changing protobuf schemas.

## Design

MLXLMCommon's default `LLMModel.prepare` interprets the `windowSize` parameter
as the prompt prefill step size and defaults to 512. Gemma4's model attention
sliding window is read separately from model config (`sliding_window=512`) and
is not replaced by this worker step.

This slice changes the control-plane request policy only:

- `estimatedPromptTokens < 32_768`: request `prefillStepSize=512`.
- `estimatedPromptTokens >= 32_768`: request `prefillStepSize=1024`.
- Vision-bearing prompts: keep the existing boundary-safe step target.

## Performance Probes And Success Metrics

Primary 128k probes:

- `http.ttfd_ms`
- `swift_text.prefill_ms`
- `swift_text.decode_ttft_ms`
- `swift_text.worker_prefill_requested_step_tokens`
- `swift_text.worker_prefill_effective_window_tokens`
- `swift_text.prefill_prompt_tokens`
- `swift_text.peak_resident_bytes`
- `swift_text.active_memory_bytes`
- `scheduler.prefill_chunk_target_tokens`
- scenario TTFT, total latency, decode tok/s, aggregate tok/s, and errors

Success criteria for keeping the change:

- 128k Melix requests remain `2/2` successful with no context, memory, quadratic
  guard, or RPC errors.
- `swift_text.worker_prefill_requested_step_tokens` and
  `swift_text.worker_prefill_effective_window_tokens` report 1024 in the 128k
  scenario.
- TTFT and `swift_text.prefill_ms` improve versus the current-origin baseline
  without a material decode tok/s regression.
- Peak resident memory remains within the current host envelope.

Rollback criteria:

- Any long-context correctness failure or worker crash.
- Material decode throughput regression.
- Memory pressure or peak RSS increase large enough to make the 128k path less
  reliable than the 512-token baseline.

## Verification

Focused local verification:

```bash
swift test --package-path services/control-plane-swift --filter 'RequestCoordinatorTests/chunkedPrefillsEmitProgressEventsAndSchedulerMetricsForLongPrompts|RequestCoordinatorTests/longTextPrefillsWidenWorkerPrefillStepWithoutChangingSchedulerProgressChunks|RequestCoordinatorTests/longTextWorkerPrefillStepThresholdIsInclusiveAt32768EstimatedTokens'
```

Performance verification:

- Run the 128k Gemma E4B serving scenario from this branch with the same model,
  prompt target, output target, ports, warmup, repeats, memory snapshots, and
  acceleration evidence as the June 4 comparison.
- Compare against a current `origin/main` baseline built in release mode from
  the same host state.
- Use the runtime-only helper at
  `.runtime/serving-comparison/swift-prefill-step-ab/scripts/run_melix_prefill_ab.py`
  to run the baseline and optimized Melix stacks sequentially. The helper
  refuses to run formal measurements when another Melix runtime, OMLX, SwiftLM,
  or heavy Swift build/test process is active, unless the operator explicitly
  asks for contaminated diagnostic numbers.

## Measurement Log

### 1024-token worker step pilot

Run:

`/Users/chenyu/Documents/github/melix/.runtime/worktrees/swift-prefill-optimization-20260604/.runtime/serving-comparison/swift-prefill-step-ab/runs/20260604T185637+0900-melix-prefill-step-ab`

Notes:

- This was run before the branch was synced from `041e82f6` to `4df62095`.
  The intervening `origin/main` change touched the macOS menu bar and window UI
  plan, not the Swift control-plane request path.
- Host guard was clean for local serving resources; only remote semantic judge
  wrapper processes were present as advisories.
- Scenario was 128k prompt target, 512 output cap, one warmup, two formal
  repeats, concurrency 1, cold-unique saturating prompts.

Results:

- Baseline and optimized both completed `2/2` requests with no context, memory,
  quadratic guard, or RPC errors.
- Baseline worker step was 512 tokens; optimized worker step was 1024 tokens.
- Client TTFT p50 improved from `34.02s` to `32.83s`, a `1.19s` or `3.50%`
  reduction.
- Total latency p50 improved from `47.38s` to `46.20s`, a `1.18s` or `2.49%`
  reduction.
- Client decode throughput was effectively unchanged: `38.34` tok/s baseline
  versus `38.32` tok/s optimized.
- Worker prefill time improved from `33.19s` to `31.30s`; worker prefill chunks
  dropped from 129 to 65.
- Peak resident memory was flat: about `8.316 GB` baseline versus `8.315 GB`
  optimized.

Conclusion:

- 1024 is a viable long-text step candidate. Because the 1024 result improved
  TTFT without a client-visible decode regression or memory increase, run one
  additional 2048-token experiment on current `origin/main` before selecting the
  final policy.

### 2048-token worker step experiment

Run:

`/Users/chenyu/Documents/github/melix/.runtime/worktrees/swift-prefill-optimization-20260604/.runtime/serving-comparison/swift-prefill-step-ab/runs/20260604T191050+0900-melix-prefill-step-ab`

Notes:

- This run used current `origin/main` at `4df62095` for both the baseline and
  optimized worktrees.
- Host guard passed before measurement. A separate worktree started lightweight
  pre-commit integration-test worker processes after the guard passed, so this
  run is useful for directional comparison but should not override a cleaner
  1024 result unless the benefit is clear.
- Scenario matched the 1024 pilot: 128k prompt target, 512 output cap, one
  warmup, two formal repeats, concurrency 1, cold-unique saturating prompts.

Results:

- Baseline and optimized both completed `2/2` requests with no context, memory,
  quadratic guard, or RPC errors.
- Baseline worker step was 512 tokens; optimized worker step was 2048 tokens.
- Client TTFT p50 improved from `33.70s` to `32.64s`, a `1.06s` or `3.13%`
  reduction.
- Total latency p50 improved from `47.06s` to `46.05s`, a `1.01s` or `2.14%`
  reduction.
- Client decode throughput moved from `38.33` tok/s baseline to `38.20` tok/s
  optimized, a `0.35%` reduction.
- Worker prefill time improved from `32.64s` to `31.09s`; worker prefill chunks
  dropped from 129 to 33.
- Worker decode metrics were weaker than baseline (`decode_ttft_ms` 634 to
  1241; `decode_ms` 14004 to 14627), while peak resident memory stayed within
  the existing envelope.

Final decision:

- Keep the final long-text worker step at 1024 tokens. The 2048-token experiment
  reduced worker prefill chunk count further, but it did not improve
  end-to-end TTFT beyond the 1024 pilot and showed slightly weaker decode-side
  metrics. 1024 is the better conservative policy for this slice.
- After the measurements, the worktree was synced to `origin/main` at
  `1450c8f2`. The new upstream changes touched Python worker native MTP,
  report-evidence, and macOS app packaging paths, not the Swift control-plane
  prefill-step policy. The final focused control-plane tests still passed after
  this sync.
