# P2-M4 Decode and Speculative Runtime Implementation Plan

**Goal:** Replace the Swift text worker's placeholder `Decode` RPC with a real resumed decode path, then add a measurable speculative-decode policy for the deterministic backend without destabilizing the default Swift MLX path.

**Scope:** This milestone is limited to worker-side decode execution, lifecycle cleanup, acceleration-policy handling, and worker-local metrics. It does not yet widen the control-plane queue model or land accelerated prefill or active-path KV quantization behavior.

## Context

- Phase plan: `docs/plans/2026-03-27-phase-2-text-runtime-depth.md`
- Milestone ladder: `docs/plans/2026-03-28-post-phase-0-coding-milestones.md`
- Relevant code:
  - `services/mlx-text-worker-swift/Sources/Core/Runtime/*`
  - `services/mlx-text-worker-swift/Sources/Core/Inference/*`
  - `services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift`
  - `services/mlx-text-worker-swift/Tests/CoreTests/WorkerScaffoldTests.swift`

## Non-Goals

- Route decode through the control plane or public HTTP APIs.
- Implement draft-model speculative decode on the real Swift MLX backend.
- Land accelerated-prefill or active-path KV quantization behavior.
- Change cache persistence or session recovery behavior.

## Performance Probes

- `swift_text.decode_ttft_ms`
- `swift_text.decode_ms`
- `swift_text.decode_tokens_per_second`
- `swift_text.decode_stream_event_count`
- `swift_text.speculative_acceptance_rate`
- `swift_text.speculative_rollback_rate`

## Work Plan

### Task 1: Add worker-local decode runtime interfaces

- Extend the text runtime protocol with a decode path that consumes stored prefill context.
- Add summary fields needed to report speculative acceptance and rollback counts.
- Keep the existing `Generate` path stable.

### Task 2: Implement real decode lifecycle in the worker registry

- Add a registry transition that consumes a stored decode handle, marks decode activity as active, and releases state on terminal completion.
- Return structured `not_found` failures for unknown decode handles.
- Preserve runtime stats for active decode state.

### Task 3: Implement `Decode` RPC streaming

- Add a dedicated decode engine.
- Emit ordered `DecodeStarted`, `TokenDelta`, `UsageDelta`, `Completed`, and structured error events.
- Record decode TTFT, total decode time, tokens per second, and stream event counts.

### Task 4: Add deterministic speculative decode

- Support `ACCELERATION_MODE_SPECULATIVE_DECODE` in the deterministic backend.
- Record acceptance and rollback metrics from the deterministic path.
- Keep unsupported real-Swift speculative requests on explicit capability boundaries instead of silently pretending they are accelerated.

### Task 5: Add worker tests and evidence

- Replace the existing decode-unimplemented test with real decode tests.
- Cover baseline decode, missing decode handle, lifecycle cleanup, abort during decode, and deterministic speculative metrics.
- Keep touched-scope coverage at or above `95%`.

## Verification

```bash
swift test --package-path services/mlx-text-worker-swift
make swift-test
make py-test
make integration-test
make coverage
git diff --check
```

## Acceptance

- `Decode` streams from stored prefill context rather than returning `unimplemented`.
- Stored prefill state is released after decode completion or failure.
- Deterministic speculative decode records non-zero acceptance and rollback metrics.
- The changed worker scope remains at or above `95%` measured coverage.
