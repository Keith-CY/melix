# P2-M3 Prefill Runtime Plan

**Goal:** Implement the first real Phase 2 worker-side `Prefill` path in the Swift text worker so prompt processing can run independently of `Generate`, return a reusable `decode_handle`, and expose prefill metrics and in-flight runtime stats without yet landing `Decode`.

**Architecture:** This slice is worker-runtime-first. Melix keeps the Phase 1 `Generate` path stable, but adds a dedicated prefill context layer inside the Swift text worker. The worker becomes responsible for materializing request-local prefill state, tracking active prefill work, and returning a decode handle that later Phase 2 slices can resume through `Decode`.

**Tech Stack:** Swift 6, Swift Package Manager, MLX Swift bindings, SwiftProtobuf-generated worker types, XCTest.

## Non-Goals

- Implement live `Decode`.
- Route control-plane HTTP traffic through the new `Prefill` RPC.
- Add speculative decode, accelerated prefill, or active KV quantization behavior.
- Persist prefill contexts across worker restarts.
- Introduce Phase 3 cache tiers or snapshot portability.

## Context

- Relevant specs:
  - `docs/architecture-spec.md`
  - `docs/worker-rpc-schema.md`
  - `docs/plans/2026-03-27-phase-2-text-runtime-depth.md`
  - `docs/plans/2026-03-28-p2-m1-phase-aware-protocol-shapes.md`
  - `docs/plans/2026-03-28-p2-m2-scheduler-lane-read-model.md`
- Relevant code paths:
  - `services/mlx-text-worker-swift/Sources/Core/Runtime/*`
  - `services/mlx-text-worker-swift/Sources/Core/Inference/*`
  - `services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift`
  - `services/mlx-text-worker-swift/Sources/Core/WorkerServices.swift`
  - `services/mlx-text-worker-swift/Tests/CoreTests/*`

## Assumptions

- The existing `Generate` RPC remains the default live path while `Prefill` becomes a worker-local primitive for later Phase 2 slices.
- A decode handle only needs to survive within the worker process during this slice.
- The minimum reusable state can stay request-local and in-memory as long as it is cleaned up on failure or future decode consumption.
- The worker runtime stats should show active prefill work even before the control plane uses queued prefill execution.

## Performance Probes and Metrics

Required probes introduced or wired in this slice:

- `swift_text.prefill_ms`
- `swift_text.prefill_prompt_tokens`
- `swift_text.prefill_context_count`

Metrics report requirements:

- live decode-resume latency remains `N/A`, because this slice does not yet implement `Decode`
- worker tests must prove prefill context creation, in-flight runtime stats, and error behavior

## Work Plan

### Task 1: Add reusable prefill runtime state

**Objective**

Extend the Swift text runtime so backends can execute prompt preparation independently and return reusable prefill context.

**Files**

- `services/mlx-text-worker-swift/Sources/Core/Runtime/TextRuntime.swift`
- `services/mlx-text-worker-swift/Sources/Core/Runtime/SwiftMLXBackend.swift`
- `services/mlx-text-worker-swift/Sources/Core/Runtime/DeterministicTextBackend.swift`

**Implementation**

- add a runtime-level prefill result and reusable prefill context shape
- teach deterministic and Swift MLX backends to execute prompt preparation without starting decode
- keep the `Generate` path compatible with the existing Phase 1 behavior

### Task 2: Store decode handles and prefill state in the worker registry

**Objective**

Make the worker registry own live prefill contexts and active prefill accounting.

**Files**

- `services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift`
- `services/mlx-text-worker-swift/Sources/Core/MetricsStore.swift`

**Implementation**

- generate worker-local decode handles
- track active prefill count and in-memory prefill contexts
- expose runtime-stat visibility and internal accessors needed by tests and the next decode milestone

### Task 3: Implement the `Prefill` RPC

**Objective**

Replace the unary `Prefill` placeholder with a real worker RPC that returns prompt tokens, decode handle, lifecycle metadata, and structured errors.

**Files**

- `services/mlx-text-worker-swift/Sources/Core/Inference/*`
- `services/mlx-text-worker-swift/Sources/Core/WorkerServices.swift`
- `services/mlx-text-worker-swift/Tests/CoreTests/*`

**Implementation**

- add a dedicated prefill engine or equivalent service path
- return `not_found` for unknown model handles and `runtime_error` for backend failures
- record prefill metrics and preserve active-prefill visibility while work is in flight

## Verification

```bash
make swift-test
make py-test
make integration-test
make coverage
```

## Acceptance

- `Prefill` returns a real success response for a loaded model
- successful prefill can return a reusable `decode_handle`
- runtime stats show active prefill work while a prefill request is executing
- `Generate` remains stable for existing Phase 1 callers
- touched scope stays at or above `95%` measured coverage
