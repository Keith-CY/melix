# Phase 2 Text Runtime Depth and Acceleration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deepen the default Swift text path from end-to-end `Generate` into phase-aware and acceleration-aware text execution with real `Prefill`, `Decode`, lane-aware scheduling, speculative decoding, accelerated prefill, and correct abort behavior across the full request lifecycle.

**Architecture:** Melix keeps the Swift control plane as scheduling and orchestration truth and extends the Swift text worker into a phase-aware and acceleration-aware text engine. The control plane becomes responsible for queue lanes, admission state, acceleration policy selection, and request lifecycle observability, while the Swift text worker becomes responsible for resumable prefill/decode execution, draft-model speculative decode, accelerated prefill behavior, and phase-aware cancellation.

**Tech Stack:** Swift 6, Swift Package Manager, MLX Swift bindings, gRPC over Unix Domain Sockets, SwiftProtobuf-generated protocol artifacts, XCTest, existing integration harness under `tests/integration`.

---

## Goal

Deliver a production-shaped Phase 2 implementation that adds real `Prefill` and `Decode` execution to the Swift text worker, replaces simple FIFO routing with lane-aware scheduling, introduces text acceleration modes such as draft-model speculative decode and accelerated prefill, and exposes queued, prefill, decode, and abort state through the control plane without changing the public API set.

## Non-Goals

- Implement cache persistence, snapshots, or resume state beyond what is needed to support live prefill/decode flow.
- Add new external endpoints beyond the existing Phase 0/1 surface.
- Move embeddings, rerank, multimodal, or image workloads into the Swift text worker.
- Introduce L2 cache persistence, branch graph recovery, or checkpoint portability across restarts.
- Build rich operator UI flows for scheduler internals in this phase.
- Add full model-operations, HuggingFace, or training workflows beyond the policy hooks needed for later phases.

## Context

- Relevant specs:
  - `docs/architecture-spec.md`
  - `docs/control-plane-protocol.md`
  - `docs/worker-rpc-schema.md`
  - `docs/phase-roadmap.md`
  - `docs/plans/2026-03-27-phase-1-swift-text-worker.md`
- Relevant code paths:
  - `services/control-plane-swift/Sources/Requests`
  - `services/control-plane-swift/Sources/EnginePool`
  - `services/control-plane-swift/Sources/Metrics`
  - `services/control-plane-swift/Sources/WorkerClient`
  - `services/mlx-text-worker-swift/Sources/Engine`
  - `services/mlx-text-worker-swift/Sources/Runtime`
  - `packages/protocol/schema/controlplane/v1/*.proto`
  - `packages/protocol/schema/worker/v1/*.proto`
  - `tests/integration`
- Current constraints:
  - Phase 1 only guarantees `Generate` and `Abort` on the Swift text path.
  - Current request scheduling assumes a thin-path text lane rather than true phase-aware admission.
- Queue and progress observability remain shallow compared with the control-plane protocol design.
  - Text acceleration modes such as draft-model decode and accelerated prefill are not yet modeled in worker or control-plane policy.

## Assumptions

- Phase 1 has already made the Swift text worker the default text engine.
- The Swift text worker can retain short-lived request state needed to continue from prefill into decode.
- The public chat endpoint remains stable while internal execution moves from monolithic `Generate` toward explicit prefill/decode phases.
- Admission control remains centralized in the control plane rather than delegated to workers.
- The first low-bit active-path KV cache modes may land here only as execution-policy hooks and runtime behavior; durable cache tiers still belong to Phase 3.

## Performance Probes and Metrics

Required probes:

- `scheduler.admission_latency_ms`
- `scheduler.queue_delay_ms`
- `scheduler.active_lane_depth`
- `swift_text.prefill_ms`
- `swift_text.decode_ttft_ms`
- `swift_text.decode_tokens_per_second`
- `swift_text.abort_queued_ms`
- `swift_text.abort_prefill_ms`
- `swift_text.abort_decode_ms`
- `swift_text.speculative_acceptance_rate`
- `swift_text.speculative_rollback_rate`
- `swift_text.accelerated_prefill_gain_pct`
- `swift_text.active_kv_quantization_ratio`

Required comparison report:

- Phase 1 generate-only path vs Phase 2 phase-aware path on the same prompt class
- queue delay and TTFT under single-request and multi-request load
- abort latency in queued, prefill, and decode states
- baseline decode vs draft-model speculative decode
- baseline prefill vs accelerated-prefill mode on repetitive or structured prompts

## Work Plan

### Task 1: Extend control-plane and worker protocols for phase-aware execution and acceleration policy

**Objective**

Make the protocol surface explicitly model `Prefill`, `Decode`, admission state, queue state, progress phases, and acceleration-policy selection without introducing wire-shape drift between control plane and worker.

**Files**

- Modify: `packages/protocol/schema/worker/v1/inference.proto`
- Modify: `packages/protocol/schema/worker/v1/common.proto`
- Modify: `packages/protocol/schema/controlplane/v1/control_plane.proto`
- Regenerate: `packages/protocol/swift/**/*`
- Regenerate: `packages/protocol/python/**/*`

**Implementation**

- Promote `Prefill` and `Decode` from placeholder RPCs to real Phase 2 contract shapes.
- Add phase-aware request progress payloads for queued, admitted, prefill, decode, completed, aborted, and failed states.
- Add acceleration-policy fields for baseline decode, draft-model speculative decode, accelerated-prefill or prompt-lookup mode, and active KV-cache quantization policy.
- Add queue and lane summary data needed by the control plane event model.
- Keep shared request identity and scheduling-hint fields consistent with the Phase 1 worker contract.

**Verification**

- `make proto`
- `swift build --package-path packages/protocol/swift`
- `make py-test`

**Acceptance**

- Generated Swift and Python outputs expose the same Phase 2 protocol vocabulary.
- The protocol clearly distinguishes queued, prefill, decode, and terminal states.

### Task 2: Add lane-aware scheduling, admission state, and acceleration policy to the control plane

**Objective**

Replace thin-path FIFO admission with a scheduler that can reason about interactive decode vs prefill work, choose acceleration modes, and surface queue state back to the operator plane.

**Files**

- Create or modify: `services/control-plane-swift/Sources/EnginePool/*`
- Create or modify: `services/control-plane-swift/Sources/Requests/*`
- Create or modify: `services/control-plane-swift/Sources/Metrics/*`
- Modify tests under `services/control-plane-swift/Tests/ControlPlaneTests`

**Implementation**

- Introduce lane-aware admission for at least interactive decode, hot prefill, and background prefill classes.
- Add policy selection for when speculative decode, accelerated prefill, or active-path KV-cache quantization should be enabled.
- Track queued, active, rejected, and completed request state with sequence-safe events.
- Make the request coordinator phase-aware so it can move a request from queue to prefill to decode.
- Expose queue depth, active lane occupancy, and backpressure state to the existing control-plane snapshot path.

**Verification**

- `swift test --package-path services/control-plane-swift --filter ControlPlane`

**Acceptance**

- The control plane can report queue and lane state without guessing from worker behavior.
- Admission decisions are deterministic and test-covered.

### Task 3: Implement real `Prefill`, `Decode`, and acceleration modes in the Swift text worker

**Objective**

Turn the Swift text worker into a phase-aware runtime that can execute explicit prefill, hold intermediate state, continue through decode, and apply acceleration modes where selected by control-plane policy.

**Files**

- Modify: `services/mlx-text-worker-swift/Sources/Runtime/*`
- Modify: `services/mlx-text-worker-swift/Sources/Engine/*`
- Modify: `services/mlx-text-worker-swift/Sources/RPCServer/*`
- Modify: `services/mlx-text-worker-swift/Sources/Abort/*`
- Add tests under `services/mlx-text-worker-swift/Tests/InferenceTests`

**Implementation**

- Replace placeholder `Prefill` and `Decode` responses with real worker execution.
- Materialize only the minimum in-memory state needed to resume decode after prefill within the same live request.
- Add draft-model speculative decode support.
- Add accelerated-prefill or prompt-lookup behavior for repetitive structured prompts where supported by the runtime.
- Add the first active-path low-bit KV-cache mode where the runtime can support it safely.
- Keep `Generate` available as a compatibility wrapper that delegates to the new phased path where appropriate.
- Ensure request-local state is released on completion, abort, or failure.

**Verification**

- `swift test --package-path services/mlx-text-worker-swift --filter Inference`

**Acceptance**

- The Swift text worker can accept `Prefill` followed by `Decode` for the same live request context.
- Worker state is not leaked after terminal events.

### Task 4: Wire abort, progress, and observability across the full request lifecycle

**Objective**

Make abort semantics correct and operator-visible in every phase rather than only during active token streaming.

**Files**

- Modify: `services/control-plane-swift/Sources/HTTPGateway/**/*`
- Modify: `services/control-plane-swift/Sources/Requests/**/*`
- Modify: `services/control-plane-swift/Sources/XPCService/**/*`
- Modify: `services/mlx-text-worker-swift/Sources/Abort/**/*`
- Modify related tests in `services/control-plane-swift/Tests/HTTPGatewayTests`

**Implementation**

- Support abort for queued, admitted, prefill, and decode states.
- Emit ordered progress and terminal events to HTTP/SSE and operator subscribers.
- Distinguish user-driven abort from scheduler rejection and runtime failure in both metrics and surfaced error state.
- Preserve existing public HTTP semantics while enriching internal progress evidence.

**Verification**

- `make swift-test`
- `make integration-test`

**Acceptance**

- Abort behavior is explicit, phase-correct, and integration-tested.
- Progress events are observable and stable from queue entry through terminal state.

### Task 5: Refresh integration coverage, workflow, and phase evidence

**Objective**

Leave Phase 2 with reproducible evidence for queueing, phased execution, and abort behavior under load.

**Files**

- Modify: `tests/integration/test_live_http_path.py`
- Create or modify additional integration tests under `tests/integration`
- Modify: `scripts/dev_up.sh`
- Modify: `scripts/dev_down.sh`
- Modify or create: `docs/runbooks/*`

**Implementation**

- Add dedicated integration cases for queued admission, prefill/decode flow, and abort in every phase.
- Add benchmark cases for speculative decode and accelerated-prefill modes.
- Add a reproducible local dev workflow that can surface lane and queue evidence.
- Record the required metrics report layout for Phase 2 hot-path measurements, including speculative acceptance and prefill gain.

**Verification**

- `make swift-test`
- `make py-test`
- `make integration-test`
- `make coverage`
- `bash scripts/dev_up.sh`
- `bash scripts/dev_down.sh`

**Acceptance**

- The touched scope stays at or above `95%` measured coverage.
- The Phase 2 metrics report includes non-`N/A` scheduling and phase-aware runtime data.

## Verification

```bash
make proto
swift build --package-path packages/protocol/swift
swift test --package-path services/mlx-text-worker-swift
make swift-test
make py-test
make integration-test
make coverage
```

Expected evidence:

- protocol generation succeeds with Phase 2 request lifecycle shapes
- the Swift text worker passes dedicated prefill/decode tests
- the control plane passes scheduling and progress tests
- integration covers queueing, phased execution, and abort
- touched-scope coverage is at least `95%`
- the metrics report contains queue delay, TTFT, TPS, abort timings, and acceleration-mode measurements

## Acceptance Criteria

- Melix supports real phase-aware text execution through explicit `Prefill` and `Decode`.
- The control plane admits work by lane rather than by simple FIFO assumptions.
- Queue, prefill, decode, and terminal states are observable through the existing control-plane surfaces.
- Abort semantics are correct and tested across queued, prefill, and decode states.
- Phase 2 concludes with reproducible metrics evidence for scheduler, runtime, and acceleration behavior.

## Rollback or Safe Exit

- Land the work in slices that preserve the Phase 1 `Generate` path until phase-aware execution is verified.
- Keep the control plane capable of falling back to the simpler Phase 1 execution path during the migration branch, but remove that compatibility path before calling Phase 2 complete.
- If phased execution cannot meet correctness or latency gates, stop after the last working protocol or scheduler slice and keep Phase 1 behavior as the active route.
