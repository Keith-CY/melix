# P2-M5 Accelerated Prefill and Active KV Mode Implementation Plan

**Goal:** Make the Swift text worker honor accelerated-prefill and active-KV acceleration policy in the prefill path, then emit measurable worker-local evidence for prefill gain and KV quantization ratio without widening the public API surface.

**Scope:** This milestone is limited to worker-side prefill behavior, acceleration-policy normalization, cache-quantization policy application, and worker-local metrics plus tests. It does not yet widen the control-plane queue model, add cache persistence, or add new integration endpoints.

## Context

- Phase plan: `docs/plans/2026-03-27-phase-2-text-runtime-depth.md`
- Milestone ladder: `docs/plans/2026-03-28-post-phase-0-coding-milestones.md`
- Relevant code:
  - `services/mlx-text-worker-swift/Sources/Core/Inference/TextPrefillEngine.swift`
  - `services/mlx-text-worker-swift/Sources/Core/Runtime/*`
  - `services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift`
  - `services/mlx-text-worker-swift/Sources/Core/MetricsStore.swift`
  - `services/mlx-text-worker-swift/Tests/CoreTests/WorkerScaffoldTests.swift`

## Non-Goals

- Route accelerated-prefill policy through the control plane or HTTP layer.
- Add Phase 3 cache persistence, snapshot restore, or disk tiers.
- Implement real draft-model speculative decode on the Swift MLX backend.
- Expand runtime capability schemas or public protocol shapes.

## Performance Probes

- `swift_text.prefill_ms`
- `swift_text.prefill_prompt_tokens`
- `swift_text.accelerated_prefill_gain_pct`
- `swift_text.active_kv_quantization_ratio`
- `swift_text.prefill_context_count`

## Work Plan

### Task 1: Normalize prefill acceleration policy in the worker runtime

- Extend the runtime prefill contract so backends can return the applied acceleration policy instead of forcing the RPC layer to guess.
- Normalize baseline, accelerated-prefill, and active-KV quantization profiles consistently before the prefill response is emitted or stored for decode.
- Keep unsupported modes on explicit capability boundaries rather than silently pretending they were applied.

### Task 2: Implement deterministic accelerated-prefill behavior

- Add measurable accelerated-prefill behavior to the deterministic backend.
- Use prompt-shape or hint-aware delay reduction so repeated structured prompts show a lower prefill path than baseline.
- Emit worker-local gain and active-KV ratio metadata for deterministic validation and benchmarks.

### Task 3: Apply active-KV policy to the Swift MLX prefill path

- Carry active-KV quantization policy into prepared prefill state so resumed decode inherits the quantized cache mode.
- Keep the Swift backend correctness-preserving by using runtime parameters and cache quantization hooks rather than fake shortcuts.
- Leave speculative decode behavior unchanged from `P2-M4`.

### Task 4: Record metrics and surface applied policy through the prefill RPC

- Record `swift_text.accelerated_prefill_gain_pct` and `swift_text.active_kv_quantization_ratio` in the worker metrics store.
- Return the applied policy in `PrefillResponse.appliedAcceleration`.
- Store the applied policy with the decode handle so resumed decode sees the normalized prefill-time result.

### Task 5: Add worker coverage for accelerated prefill and active-KV mode

- Cover deterministic accelerated-prefill gain.
- Cover active-KV quantization ratio reporting.
- Cover prefill RPC policy normalization and stored-context propagation.
- Keep touched worker scope coverage at or above `95%`.

## Verification

```bash
swift test --package-path services/mlx-text-worker-swift
swift test --package-path services/mlx-text-worker-swift --enable-code-coverage
make swift-test
make py-test
make integration-test
git diff --check
```

## Acceptance

- `Prefill` returns the applied acceleration policy rather than echoing an unverified request policy.
- Deterministic accelerated-prefill reports a non-zero gain metric for repetitive structured prompts.
- Active-KV quantization policy reports a non-zero ratio metric when enabled.
- The changed worker scope remains at or above `95%` measured coverage.
