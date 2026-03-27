# Phase 1 Swift Text Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Phase 0 Python-backed default text path with an independent Swift text worker that serves the default `Generate` hot path over the shared worker RPC boundary.

**Architecture:** Melix keeps the Swift control plane as orchestration truth and adds a separate `mlx-text-worker-swift` service for text-only runtime execution. The control plane routes default text traffic to the Swift worker over native local RPC, keeps Python workers for non-text families, and fails explicitly when the Swift text engine cannot serve a request.

**Tech Stack:** Swift 6, Swift Package Manager, MLX Swift bindings, gRPC over Unix Domain Sockets, SwiftProtobuf-generated protocol models, generated Swift worker RPC stubs, XCTest, existing Python worker for compatibility and integration contrast.

---

## Goal

Deliver a production-shaped Phase 1 implementation that makes the Swift text worker the default engine for `POST /v1/chat/completions` without changing the public HTTP or XPC surface.

## Non-Goals

- Implement `Prefill`, `Decode`, cache mutation, snapshots, or maintenance RPCs in the Swift worker.
- Move multimodal, embeddings, rerank, image, audio, convert, doctor, or bench workloads out of the Python worker.
- Add desktop dashboard, chat, image, HuggingFace, quantization, or training workflows beyond the protocol hooks needed for later phases.
- Embed text runtime execution inside the Swift control plane process.
- Introduce silent fallback from the Swift text worker to the Python text path.
- Expand Phase 0 public endpoints beyond the existing `/v1/chat/completions` and `/v1/models` slice.

## Context

- Relevant specs:
  - `docs/architecture-spec.md`
  - `docs/worker-rpc-schema.md`
  - `docs/repo-skeleton.md`
  - `docs/phase-roadmap.md`
  - `docs/decisions/2026-03-27-swift-text-runtime.md`
- Relevant code paths:
  - `services/control-plane-swift/Sources/Bootstrap/main.swift`
  - `services/control-plane-swift/Sources/WorkerClient/WorkerClient.swift`
  - `services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift`
  - `services/control-plane-swift/Sources/Requests/RequestCoordinator.swift`
  - `services/mlx-worker-python/worker/grpc_server.py`
  - `services/mlx-worker-python/worker/engine/engine_core.py`
  - `services/mlx-worker-python/worker/runtime/mlx_text_runtime.py`
  - `packages/protocol/schema/worker/v1/*.proto`
  - `buf.gen.yaml`
- Current constraints:
  - The live text path still depends on `PythonBridgeWorkerClient`.
  - Swift code generation currently produces protobuf messages only; there are no Swift worker RPC stubs yet.
  - The Phase 0 deterministic path must remain the default integration path until the Swift text worker has stable smoke coverage.
  - The control plane currently assumes a single worker client for the active text path.
  - The gRPC Swift v2 runtime used for shared Swift worker stubs requires a macOS 15 package baseline for the Swift protocol, control-plane, and desktop workspaces.
  - Later phases will need protocol room for speculative decode, accelerated prefill, cache tiers, model operations, and richer desktop workflows.

## Assumptions

- The Swift text worker will speak the existing Melix worker RPC contract over Unix Domain Sockets.
- The Swift text worker will support `RuntimeService.Handshake`, `LoadModel`, `UnloadModel`, `ListLoadedModels`, `GetRuntimeStats`, `InferenceService.Generate`, and `InferenceService.Abort` in Phase 1.
- Unsupported Phase 2+ RPCs exposed by the shared contract will return structured `unimplemented`.
- A Swift-native MLX runtime path is available for model load and token streaming on Apple Silicon.
- The Python text path may remain in the repository for targeted validation and debugging, but it is not a fallback path in normal control-plane routing.
- `MELIX_DEV_TEXT_MODEL_PATH` remains the model source override for live MLX smoke verification.
- Phase 1 protocol and routing work must not block later speculative decode, cache quantization, HuggingFace sync, or model-operations commands from fitting into the same shared contracts.

## Performance Probes and Metrics

Phase 1 design and implementation must include instrumentation for the Swift hot path before the work is considered complete.

Required probes:

- `swift_text.load_model_ms`
- `swift_text.ttft_ms`
- `swift_text.tokens_per_second`
- `swift_text.abort_ms`
- `swift_text.stream_event_count`
- `swift_text.peak_resident_bytes`
- `control_plane.worker_route_ms`
- `control_plane.worker_connect_ms`

Required comparison report:

- Swift text worker vs current Python text path on the same prompt class and model source
- deterministic integration path vs Swift live MLX path for request translation overhead
- explicit `N/A` is not acceptable for the Swift hot-path metrics in this phase

## Work Plan

### Task 1: Add Swift worker RPC generation and package baseline

**Objective**

Make the protocol toolchain capable of generating Swift-side worker service stubs so the Swift text worker can implement the shared RPC contract without hand-written transport models.

**Files**

- Modify: `buf.gen.yaml`
- Modify: `scripts/proto_gen.sh`
- Modify: `Makefile`
- Modify: `packages/protocol/swift/Package.swift`
- Create or modify generated outputs under `packages/protocol/swift/`

**Implementation**

- Add Swift worker RPC code generation alongside the existing Swift protobuf message generation.
- Keep `packages/protocol/schema` as the only editable interface source of truth.
- Extend the Swift protocol package so both the control plane and the Swift worker can depend on generated protobuf models and generated RPC stubs.
- Keep Python generation unchanged so mixed-language workers still share one protocol family.

**Verification**

- `make proto`
- `swift build --package-path packages/protocol/swift`

**Acceptance**

- Swift packages can import worker protobuf models and worker RPC client or server stubs from generated code.
- No manually maintained transport duplicates are added for the shared worker RPC surface.

### Task 2: Create the `mlx-text-worker-swift` service skeleton

**Objective**

Introduce a dedicated Swift executable service that can bootstrap, listen on a worker socket, report capabilities, and own text-runtime lifecycle boundaries without depending on the control plane process.

**Files**

- Create: `services/mlx-text-worker-swift/Package.swift`
- Create: `services/mlx-text-worker-swift/Sources/Bootstrap/main.swift`
- Create: `services/mlx-text-worker-swift/Sources/RPCServer/WorkerServer.swift`
- Create: `services/mlx-text-worker-swift/Sources/Runtime/TextRuntime.swift`
- Create: `services/mlx-text-worker-swift/Sources/Engine/TextEngine.swift`
- Create: `services/mlx-text-worker-swift/Sources/Models/ModelRegistry.swift`
- Create: `services/mlx-text-worker-swift/Sources/Streaming/TokenStreamWriter.swift`
- Create: `services/mlx-text-worker-swift/Sources/Abort/AbortRegistry.swift`
- Create: `services/mlx-text-worker-swift/Sources/Metrics/MetricsStore.swift`
- Create: `services/mlx-text-worker-swift/Tests/...`

**Implementation**

- Mirror the Phase 0 Python worker ownership model at the service boundary: bootstrap, runtime registry, request tracking, abort tracking, metrics, and RPC server.
- Keep the first package focused and text-only. Do not add multimodal, maintenance, or cache payload ownership beyond what is required for `Generate`.
- Define one clear request flow:
  1. RPC server receives `Generate`.
  2. Engine validates model handle and request identity.
  3. Runtime renders prompt and streams token deltas.
  4. Abort registry can stop the active request.
  5. Metrics store records lifecycle and streaming probes.

**Verification**

- `swift build --package-path services/mlx-text-worker-swift`
- `swift test --package-path services/mlx-text-worker-swift`

**Acceptance**

- The service can start independently of the control plane.
- `Handshake` and basic runtime RPCs return coherent capability and worker-state data.
- Unsupported Phase 2+ RPCs return explicit structured `unimplemented`.

### Task 3: Implement Swift text runtime lifecycle and model loading

**Objective**

Give the Swift text worker a real MLX-backed model lifecycle for the default text model, with behavior parity to the Phase 0 Python path for load, unload, and runtime stats.

**Files**

- Modify: `services/mlx-text-worker-swift/Sources/Runtime/TextRuntime.swift`
- Modify: `services/mlx-text-worker-swift/Sources/Models/ModelRegistry.swift`
- Modify: `services/mlx-text-worker-swift/Sources/Metrics/MetricsStore.swift`
- Create tests under `services/mlx-text-worker-swift/Tests/RuntimeTests/`

**Implementation**

- Implement runtime load and unload using the Swift MLX path for text models only.
- Support the Phase 0 development model contract, including `melix-dev-text` and `MELIX_DEV_TEXT_MODEL_PATH`.
- Surface `RuntimeCapabilities` that truthfully advertise the Phase 1 subset.
- Track loaded model handles, active request counts, resident memory estimates, and worker state for `GetRuntimeStats`.
- Reuse the same prompt-rendering semantics as the current Python path where possible, including tokenizer chat-template preference and fallback prompt rendering.

**Verification**

- `swift test --package-path services/mlx-text-worker-swift --filter Runtime`
- manual smoke with a configured dev model path and worker bootstrap command

**Acceptance**

- Load, unload, list, and stats paths work against a real Swift runtime implementation.
- Capability responses clearly distinguish supported and unimplemented execution paths.

### Task 4: Implement `Generate` and `Abort` end-to-end in the Swift worker

**Objective**

Make the Swift text worker capable of real streamed token generation and in-flight cancellation for the default text path.

**Files**

- Modify: `services/mlx-text-worker-swift/Sources/Engine/TextEngine.swift`
- Modify: `services/mlx-text-worker-swift/Sources/Streaming/TokenStreamWriter.swift`
- Modify: `services/mlx-text-worker-swift/Sources/Abort/AbortRegistry.swift`
- Modify: `services/mlx-text-worker-swift/Sources/RPCServer/WorkerServer.swift`
- Create tests under `services/mlx-text-worker-swift/Tests/InferenceTests/`

**Implementation**

- Implement `Generate` as the first-class streaming path.
- Emit shared `ExecuteEvent` payloads in the same order expected by the control plane:
  - `prefill_started` when prompt processing begins
  - `token_delta` during generation
  - `usage_delta` when requested
  - `completed` with `finish_reason` and final assistant text
  - `error` on runtime failure
- Record TTFT, steady-state throughput, event count, and abort latency in the metrics store.
- Implement `Abort` so queued or active generation can stop cleanly and report terminal state without leaking request state.

**Verification**

- `swift test --package-path services/mlx-text-worker-swift --filter Inference`
- manual worker-only smoke against a live model source

**Acceptance**

- `Generate` streams valid worker events over RPC.
- `Abort` stops active generation and surfaces a correct terminal state.
- Metrics probes exist for TTFT, TPS, abort latency, and peak memory.

### Task 5: Replace single-worker control-plane routing with engine-aware routing

**Objective**

Teach the control plane to route default text requests to the Swift text worker while preserving the existing public API and explicit failure semantics.

**Files**

- Modify: `services/control-plane-swift/Sources/WorkerClient/WorkerClient.swift`
- Modify: `services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift`
- Create: `services/control-plane-swift/Sources/WorkerClient/SwiftTextWorkerClient.swift`
- Create: `services/control-plane-swift/Sources/WorkerClient/WorkerRegistry.swift`
- Create or modify: `services/control-plane-swift/Sources/WorkerClient/WorkerRoute.swift`
- Modify: `services/control-plane-swift/Sources/Bootstrap/main.swift`
- Modify: `services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift`
- Modify: `services/control-plane-swift/Sources/Requests/RequestCoordinator.swift`
- Modify related tests under `services/control-plane-swift/Tests/WorkerClientTests/` and `Tests/HTTPGatewayTests/`

**Implementation**

- Replace the current “single `WorkerClient` for text” assumption with worker routing keyed by capability class and engine type.
- Add a native Swift text worker client that speaks the same worker RPC contract over local sockets.
- Keep the Python worker registered for non-text families and optional validation paths, but not as a silent text fallback.
- Update bootstrap so the control plane:
  - starts or connects to the Swift text worker
  - performs handshake and optional model preload
  - marks text route availability explicitly
- Preserve `/v1/chat/completions` and `/v1/models` behavior while sourcing default text model state from the Swift route.
- Return explicit worker-unavailable or route-unavailable errors if the Swift text worker is not healthy.

**Verification**

- `make swift-test`
- live smoke for `/v1/models`
- live smoke for streamed `/v1/chat/completions`
- live smoke for abort against the Swift text worker

**Acceptance**

- The default text route uses the Swift worker without public API changes.
- The control plane exposes explicit failures when the Swift worker cannot serve requests.
- The Python worker remains available for non-text families and targeted debugging only.

### Task 6: Refresh local workflows, integration coverage, and operator evidence

**Objective**

Make the new Phase 1 path reproducible for local development, CI, and operator troubleshooting.

**Files**

- Modify: `scripts/dev_up.sh`
- Modify: `scripts/dev_down.sh`
- Modify: `README.md`
- Modify: `docs/runbooks/...` or create a new runbook for local Swift text worker boot and recovery
- Create or modify: `tests/integration/test_live_http_path.py`
- Create or modify additional integration tests for `/v1/models`, abort, and explicit Swift-worker failure
- Modify coverage scripts or targets if needed

**Implementation**

- Add a stable developer workflow that boots the Swift text worker, the Python worker, and the control plane with predictable socket and port layout.
- Keep deterministic integration as the default CI path where appropriate, but add an optional MLX smoke path gated by `MELIX_DEV_TEXT_MODEL_PATH`.
- Extend integration tests so Phase 1 has separate evidence for:
  - `/v1/models`
  - streamed chat
  - abort
  - explicit failure when the Swift text worker is unavailable
- Document the required performance report shape and how to reproduce it locally.

**Verification**

- `make swift-test`
- `make py-test`
- `make integration-test`
- `make coverage`
- `bash scripts/dev_up.sh`
- `bash scripts/dev_down.sh`
- optional MLX smoke with `MELIX_DEV_TEXT_MODEL_PATH=...`

**Acceptance**

- Local operators can bring the full Phase 1 stack up and down reliably.
- Integration coverage includes explicit route, abort, and failure-path assertions for the Swift worker.
- The touched repository scope meets the `>=95%` coverage rule.
- A metrics report template exists and is reproducible for the Swift text path.

## Verification

```bash
make proto
swift build --package-path packages/protocol/swift
swift build --package-path services/mlx-text-worker-swift
swift test --package-path services/mlx-text-worker-swift
make swift-test
make py-test
make integration-test
make coverage
```

Expected evidence:

- protocol generation succeeds with Swift worker RPC artifacts
- the new Swift worker package builds and passes its own tests
- control-plane tests still pass after routing changes
- Python worker tests remain green for the non-text and compatibility surfaces they still own
- integration covers `/v1/models`, streamed chat, abort, and explicit worker failure
- coverage for the touched scope is at least `95%`
- the Phase 1 metrics report includes non-`N/A` Swift hot-path numbers

## Acceptance Criteria

- Melix has a dedicated `services/mlx-text-worker-swift` service implementing the Phase 1 subset of the shared worker RPC contract.
- The control plane routes default text requests to the Swift text worker by engine class rather than by Python-specific assumptions.
- `POST /v1/chat/completions` streams through the Swift worker without changing the public HTTP shape.
- Abort works end-to-end against the Swift worker.
- Swift worker failures are surfaced explicitly and do not trigger silent Python fallback.
- Development workflow, integration coverage, and metrics evidence are updated to treat the Swift text path as the default text engine.

## Rollback or Safe Exit

- Keep the Python text path callable during implementation until the Swift worker route is verified, but do not expose it as an automatic fallback.
- Land the Swift worker in slices that preserve a bootable repository after each merge: protocol generation, worker package skeleton, runtime lifecycle, generate and abort, routing switch, workflow and integration updates.
- If the Swift worker cannot satisfy performance or correctness gates, stop after the last working slice and keep the control plane on the existing Python text route while retaining the new worker package behind a non-default route flag.
