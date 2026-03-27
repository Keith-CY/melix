# P1-M2 Swift Text Worker Scaffold

**Goal:** Land the first independent `mlx-text-worker-swift` service skeleton so Melix has a production-shaped Swift worker process boundary before real Swift MLX model lifecycle and token generation are added in later Phase 1 milestones.

**Scope:** This milestone covers package bootstrap, worker configuration, runtime registry, RPC service registration, coherent `Handshake` and runtime stats responses, and explicit structured `unimplemented` behavior for unsupported Phase 1+ RPCs. It does not include real MLX model loading or token generation.

## Context

- Canonical references:
  - `docs/architecture-spec.md`
  - `docs/repo-skeleton.md`
  - `docs/worker-rpc-schema.md`
  - `docs/plans/2026-03-27-phase-1-swift-text-worker.md`
  - `docs/plans/2026-03-28-post-phase-0-coding-milestones.md`
- Current implementation state:
  - shared Swift worker protobuf and gRPC stubs are now available under `packages/protocol/swift/worker/v1/`
  - the control plane still routes text traffic to the Python-backed worker path
  - no `services/mlx-text-worker-swift/` package exists yet
- Current constraint:
  - the service scaffold must be able to evolve into a real Unix-domain-socket gRPC worker without rewriting the package boundary

## Non-Goals

- Real MLX model load or unload behavior
- Real streamed `Generate`
- Real `Abort` request cancellation
- Control-plane routing changes
- Prefill, decode, cache mutation, snapshot, maintenance, multimodal, embedding, rerank, audio, or image execution

## Assumptions

- The Swift text worker continues to use the shared worker RPC contract defined in `packages/protocol/schema/worker/v1/`.
- The package baseline remains `macOS 15`.
- The first skeleton package may report text-oriented capabilities even before load and generate are fully implemented, but it must not claim speculative decoding, continuous batching, paged cache, disk cache, or multimodal support.
- Unsupported RPCs should return structured protocol-level `unimplemented` responses rather than transport-level internal errors.

## Performance Probes

P1-M2 must introduce the initial probe surface for the worker process skeleton:

- `swift_text.bootstrap_ms`
- `swift_text.handshake_ms`
- `swift_text.runtime_stats_ms`
- `swift_text.rpc_error_count`
- `swift_text.unimplemented_rpc_count`

The metrics report for this milestone may remain skeleton-oriented rather than inference-oriented. TTFT, tokens per second, load-model latency, and peak resident memory remain out of scope until later milestones.

## Work Plan

### Task 1: Create the Swift worker package and target layout

**Objective**

Create the new executable package and give it a stable internal module boundary that matches the long-term repo skeleton.

**Files**

- Create: `services/mlx-text-worker-swift/Package.swift`
- Create: `services/mlx-text-worker-swift/Sources/Bootstrap/main.swift`
- Create: `services/mlx-text-worker-swift/Sources/Core/WorkerConfiguration.swift`
- Create: `services/mlx-text-worker-swift/Sources/Core/WorkerServer.swift`
- Create: `services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift`
- Create: `services/mlx-text-worker-swift/Sources/Core/AbortRegistry.swift`
- Create: `services/mlx-text-worker-swift/Sources/Core/MetricsStore.swift`
- Create test targets under `services/mlx-text-worker-swift/Tests/`

**Implementation**

- Create one core target and one executable bootstrap target.
- Keep the first layout small; use a single `Core` module until later milestones justify deeper target splitting.
- Depend on the shared protocol package and the official gRPC Swift runtime.
- Add the NIO HTTP/2 transport dependency so the package can host a real UDS server in later milestones without a manifest change.

**Acceptance**

- The package builds independently.
- The executable target can assemble a worker server from configuration without importing control-plane code.

### Task 2: Implement configuration, registry, and metrics primitives

**Objective**

Create the internal state holders the worker service needs before real runtime logic is added.

**Implementation**

- Add a `WorkerConfiguration` type that resolves:
  - worker id
  - socket path
  - backend mode
  - runtime version label
- Add `WorkerRuntimeRegistry` to track:
  - loaded model handles
  - active request count
  - draining state
  - static Phase-1 capability advertisement
- Add `MetricsStore` with counters and timing recording for the P1-M2 probe set.
- Add `AbortRegistry` as a placeholder request-state owner even though active generation is not implemented yet.

**Acceptance**

- Runtime stats reflect registry state.
- Capability reporting is deterministic and testable.
- Metrics counters can be incremented without depending on live runtime execution.

### Task 3: Implement RPC services with coherent Phase-1 scaffold behavior

**Objective**

Make the package satisfy the shared runtime, inference, cache, and maintenance service protocols.

**Implementation**

- Implement:
  - `Handshake`
  - `GetRuntimeStats`
  - `ListLoadedModels`
  - `Drain`
  - `Shutdown`
- Return structured `unimplemented` responses for:
  - `LoadModel`
  - `UnloadModel`
  - `WarmupModel`
  - `Generate`
  - `Prefill`
  - `Decode`
  - `Abort`
  - all cache RPCs
  - all maintenance RPCs
- Keep method behavior explicit and stable so later milestones can replace one RPC at a time.

**Acceptance**

- `Handshake` returns protocol version echo, runtime version, and coherent capabilities.
- Runtime and list RPCs return valid empty-state responses.
- Unsupported RPCs are protocol-valid and carry `code = "unimplemented"` with milestone-scoped messages.

### Task 4: Add bootstrap server assembly

**Objective**

Make the worker package able to assemble a real gRPC server object and expose a bootstrap path without requiring the full runtime implementation.

**Implementation**

- Add a bootstrap entry that:
  - reads configuration
  - creates core state objects
  - constructs the runtime, inference, cache, and maintenance service implementations
  - builds a `GRPCServer` configured for Unix-domain-socket serving
- Keep the actual long-running `serve()` path thin and isolated in bootstrap code.
- Do not start the server in unit tests; test server assembly and service registration separately.

**Acceptance**

- A server object can be created from configuration and services without crashing.
- The executable has a deterministic default socket path and worker id.

## Verification

- `swift test --package-path services/mlx-text-worker-swift`
- `swift build --package-path services/mlx-text-worker-swift`
- `git diff --check`

## Test Strategy

Use TDD for the service skeleton:

1. Add failing tests for:
   - configuration defaults
   - handshake response
   - runtime stats and empty loaded-model list
   - `Drain` state transition
   - structured `unimplemented` responses for selected runtime, inference, cache, and maintenance RPCs
2. Implement the minimum code to make those tests pass.
3. Keep real network serving out of the first test slice unless needed to validate server assembly.

## Metrics Report Contract

P1-M2 must report:

- build time for the new Swift worker package
- test time for the new Swift worker package
- measured touched-scope test coverage if available
- probe availability status for the skeleton metrics store

If meaningful touched-scope coverage is not yet measurable for the new package, report `N/A` with the specific reason and the next command needed to make it measurable.

## Rollback / Safe Exit

- The service package may land without any control-plane routing changes.
- If bootstrap transport work proves unstable, the package may temporarily land with service and registry tests only, but the package structure and service protocol implementations must still remain in place.
