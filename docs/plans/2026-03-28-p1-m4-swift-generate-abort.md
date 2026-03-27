# P1-M4 Swift Generate and Abort Hot Path

**Goal:** Replace the P1-M3 inference placeholders with a real Swift-side `Generate` streaming path and in-flight `Abort` behavior for the development text model, while preserving the shared worker RPC contract and keeping control-plane routing changes deferred to P1-M5.

**Scope:** This milestone covers prompt rendering for text chat messages, Swift MLX generation bridging, streamed `ExecuteEvent` sequencing, abort-aware request tracking, and the first live hot-path metrics for the Swift text worker. It does not implement `Prefill`, `Decode`, speculative execution, cache reuse, or control-plane route selection.

## Context

- Canonical references:
  - `docs/architecture-spec.md`
  - `docs/worker-rpc-schema.md`
  - `docs/plans/2026-03-27-phase-1-swift-text-worker.md`
  - `docs/plans/2026-03-28-post-phase-0-coding-milestones.md`
  - `docs/plans/2026-03-28-p1-m3-swift-runtime-lifecycle.md`
- Current implementation state:
  - `services/mlx-text-worker-swift/` can bootstrap, handshake, load models, unload models, and report runtime stats.
  - `Generate` still returns a structured `unimplemented` event.
  - `Abort` can only remove a placeholder request token from the scaffold registry.
  - The Python worker already defines the minimum expected event order for the Phase 0 thin path: token deltas, optional usage delta, then terminal completion or error.
  - The Swift runtime already loads MLX model containers and is ready to carry live inference state.
- Runtime dependency:
  - `MLXLMCommon.ModelContainer` exposes `prepare(input:)` and `generate(input:parameters:)`, which is the correct Swift-native entrypoint for this milestone.

## Non-Goals

- Control-plane routing changes
- Worker socket orchestration changes
- `Prefill`, `Decode`, or speculative decoding
- Cache mutation, snapshots, or block-table reuse
- Tool-calling, reasoning-stream separation, or multimodal message parts
- Desktop or operator workflow expansion beyond plan and metrics updates

## Assumptions

- Phase 1 only needs the shared text hot path: text-only chat messages, streamed assistant text, optional usage, and explicit terminal completion.
- Unsupported message parts or tool-driven inputs should fail explicitly rather than silently degrade.
- Unit tests must remain deterministic and avoid a real downloaded model by injecting a fake text generation backend.
- A live worker-only MLX smoke path may be conditional on a configured `MELIX_DEV_TEXT_MODEL_PATH`.
- `Abort` is defined as best-effort in-flight cancellation for active generation requests in this milestone; queued request cancellation remains a later scheduling concern.

## Performance Probes

P1-M4 must define and record the first true hot-path probes for the Swift text worker:

- `swift_text.ttft_ms`
- `swift_text.tokens_per_second`
- `swift_text.abort_ms`
- `swift_text.stream_event_count`
- `swift_text.generate_ms`

This milestone may keep comparison against the Python path for P1-M6, but probe availability is mandatory here.

## Work Plan

### Task 1: Add a generation abstraction and request-state tracking

**Objective**

Introduce the internal primitives needed to render a prompt, stream token deltas, and terminate active generation cleanly.

**Files**

- Create: `services/mlx-text-worker-swift/Sources/Core/Inference/TextGenerationEngine.swift`
- Modify: `services/mlx-text-worker-swift/Sources/Core/Runtime/TextRuntime.swift`
- Modify: `services/mlx-text-worker-swift/Sources/Core/Runtime/SwiftMLXBackend.swift`
- Modify: `services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift`
- Modify: `services/mlx-text-worker-swift/Sources/Core/AbortRegistry.swift`

**Implementation**

- Add a generation abstraction that can be backed by Swift MLX in production and by deterministic fake streams in tests.
- Add active-request state so the worker can:
  - validate the model handle
  - register and unregister active request IDs
  - capture emitted assistant text
  - observe cancellation without leaking request state
- Extend the runtime registry to expose the loaded runtime model needed by the generation engine.

**Acceptance**

- The worker has one internal abstraction for text generation that is testable without a real model.
- Active request tracking supports both successful completion and abort.

### Task 2: Implement `Generate` event sequencing

**Objective**

Replace the scaffold `Generate` behavior with a real streaming implementation that matches the shared worker contract and current control-plane expectations.

**Files**

- Modify: `services/mlx-text-worker-swift/Sources/Core/WorkerServices.swift`
- Create or modify: `services/mlx-text-worker-swift/Sources/Core/Inference/TextGenerationEngine.swift`
- Modify: `services/mlx-text-worker-swift/Sources/Core/MetricsStore.swift`

**Implementation**

- Render supported `ChatMessage` inputs into the Swift MLX prompt shape.
- Emit `ExecuteEvent` payloads in this order:
  1. `prefill_started`
  2. zero or more `token_delta`
  3. optional `usage_delta`
  4. terminal `completed`
- Emit `error` on validation or runtime failure instead of returning a transport error.
- Track TTFT, stream event count, overall generate duration, and token throughput.

**Acceptance**

- `Generate` no longer emits `unimplemented`.
- Successful requests stream valid token events and a correct terminal completion.
- Missing model handles or unsupported message shapes return explicit `error` events.

### Task 3: Implement `Abort`

**Objective**

Make `Abort` stop active generation and surface a correct terminal state without corrupting worker state.

**Files**

- Modify: `services/mlx-text-worker-swift/Sources/Core/AbortRegistry.swift`
- Modify: `services/mlx-text-worker-swift/Sources/Core/WorkerServices.swift`
- Modify: `services/mlx-text-worker-swift/Sources/Core/Inference/TextGenerationEngine.swift`

**Implementation**

- Replace the placeholder abort set with cancellable request tokens or equivalent state.
- Allow the generation engine to observe cancellation quickly while streaming.
- Record `swift_text.abort_ms`.
- Return `found = false` only when the request ID is unknown or already finished.

**Acceptance**

- Active generation can be aborted from another RPC call.
- Aborted requests end with `completed.finish_reason = "cancelled"` instead of hanging or crashing.

### Task 4: Lock behavior with red tests and smoke coverage

**Objective**

Use TDD to lock the hot path before implementation and keep touched-scope coverage above the repository threshold.

**Files**

- Modify or create tests under `services/mlx-text-worker-swift/Tests/InferenceTests/`
- Modify: `docs/README.md`

**Implementation**

- Add failing tests first for:
  - successful streaming with `prefill_started`, token deltas, optional usage, and final completion
  - missing model handle returning an `error` event
  - aborting an active request and producing `cancelled`
  - metrics availability for TTFT, stream event count, and abort timing
- Keep tests deterministic by injecting a fake generation backend.
- Document one worker-only live smoke command for a configured `MELIX_DEV_TEXT_MODEL_PATH`.

**Acceptance**

- The new inference tests drive the implementation instead of validating prewritten code.
- Touched-scope automated coverage remains at or above `95%`.

## Verification

- `swift test --package-path services/mlx-text-worker-swift`
- `swift test --package-path services/mlx-text-worker-swift --filter Inference`
- `swift test --package-path services/mlx-text-worker-swift --enable-code-coverage`
- `python3 scripts/swift_coverage_summary.py services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/codecov/MelixTextWorkerSwift.json /services/mlx-text-worker-swift/Sources/`
- `make swift-test`
- conditional manual worker-only smoke with a configured `MELIX_DEV_TEXT_MODEL_PATH`

## Metrics Report Contract

P1-M4 must report:

- Swift text worker inference test time
- touched-scope Swift source coverage
- TTFT, stream event count, and abort probe availability
- worker-only live MLX smoke result or explicit `N/A` reason when no model source is configured

## Rollback / Safe Exit

- If the live Swift MLX generation bridge proves unstable, the milestone may still land with the generation abstraction, deterministic inference tests, and a real `Generate` event pipeline wired to fake runtime output, but the service contract must stay ready to swap in the live MLX path without changing the worker RPC shape.
