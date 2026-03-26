# Melix Phase 0 + Thin Path Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the first executable Melix slice: generated protocol stubs, a Swift control plane daemon, a Python worker with real MLX text generation, a minimal XPC-connected menu bar shell, and one end-to-end local `POST /v1/chat/completions` streaming path with abort support.

**Architecture:** The first slice keeps the architecture honest without overbuilding. The Swift control plane owns HTTP, SSE, XPC, request translation, model state, and worker dispatch; the Python worker owns model execution and streaming token output. Scheduling, cache persistence, multimodal execution, and branch-aware recovery remain scaffolded but intentionally minimal in this phase.

**Tech Stack:** Swift Package Manager, Swift Concurrency, Swift Protobuf or grpc-swift-compatible generated types, Python 3.12+, `uv`, `grpcio`, `protobuf`, MLX text runtime, Buf or `protoc`, Unix Domain Sockets, XCTest, `pytest`.

---

### Task 1: Create the repository bootstrap and code generation baseline

**Files:**
- Create: `README.md`
- Create: `Makefile`
- Create: `Package.swift`
- Create: `pyproject.toml`
- Create: `buf.yaml`
- Create: `buf.gen.yaml`
- Create: `services/control-plane-swift/Package.swift`
- Create: `services/mlx-worker-python/pyproject.toml`
- Create: `apps/macos-menubar/Package.swift`

**Step 1: Write the failing bootstrap checks**

Create bootstrap verification tests or smoke scripts that assert:

- `make proto` resolves schema paths and runs code generation
- `make swift-test` targets the Swift workspace
- `make py-test` targets the Python worker workspace
- missing generated code or missing package manifests produce explicit failures

**Step 2: Run the bootstrap checks and confirm they fail**

Run:

```bash
make proto
make swift-test
make py-test
```

Expected:

- command failures because the manifests, generation config, and package layout do not exist yet

**Step 3: Add the minimal repo bootstrap**

Implement:

- a root `README.md` with the first-slice local developer flow
- a `Makefile` with stable targets: `bootstrap`, `proto`, `swift-test`, `py-test`, `integration-test`
- root package metadata for Swift and Python workspaces
- `buf.yaml` and `buf.gen.yaml` that generate Swift and Python code from `packages/protocol/schema`
- package manifests for the Swift daemon and menu bar app, and the Python worker project

**Step 4: Re-run the bootstrap checks**

Run:

```bash
make proto
make swift-test
make py-test
```

Expected:

- proto generation succeeds
- test commands execute the correct workspaces even if most tests are still placeholders

**Step 5: Commit**

```bash
git add README.md Makefile Package.swift pyproject.toml buf.yaml buf.gen.yaml apps/macos-menubar/Package.swift services/control-plane-swift/Package.swift services/mlx-worker-python/pyproject.toml
git commit -m "build: add Melix bootstrap and protocol generation"
```

### Task 2: Build the Swift control plane skeleton with XPC and state snapshots

**Files:**
- Create: `services/control-plane-swift/Sources/Bootstrap/main.swift`
- Create: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Create: `services/control-plane-swift/Sources/XPCService/EventSubscriptionHub.swift`
- Create: `services/control-plane-swift/Sources/WorkerClient/WorkerClient.swift`
- Create: `services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift`
- Create: `services/control-plane-swift/Sources/EnginePool/EnginePool.swift`
- Create: `services/control-plane-swift/Sources/Metrics/MetricsStore.swift`
- Create: `services/control-plane-swift/Sources/Snapshots/ServerSnapshotBuilder.swift`
- Create: `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
- Create: `services/control-plane-swift/Tests/ControlPlaneTests/EventSubscriptionHubTests.swift`

**Step 1: Write the failing Swift tests**

Add tests for:

- `handshake` returns a typed `HandshakeResponse` containing a snapshot
- `execute` handles `ServerCommand.GetServerSnapshot`
- `execute` handles `ModelCommand.ListModels`
- `subscribe` receives typed events with monotonic sequence numbers

**Step 2: Run the Swift tests and confirm they fail**

Run:

```bash
swift test --package-path services/control-plane-swift
```

Expected:

- failures because the daemon package, service implementation, and snapshot builder are not implemented yet

**Step 3: Implement the minimal control plane core**

Implement:

- daemon bootstrap and process wiring
- XPC surface with `handshake`, `execute`, `subscribe`, `unsubscribe`
- in-memory model catalog and server snapshot builder
- event subscription hub with per-subscription sequence numbers
- thin worker client placeholder that can be injected or mocked in tests

Keep this phase limited to:

- server snapshot
- list/load/unload model state
- metrics snapshot placeholder
- event fanout for server and model state changes

**Step 4: Re-run Swift tests**

Run:

```bash
swift test --package-path services/control-plane-swift
```

Expected:

- handshake, execute, and subscription tests pass

**Step 5: Commit**

```bash
git add services/control-plane-swift
git commit -m "feat: add control plane xpc skeleton"
```

### Task 3: Implement the Python worker runtime and MLX text generation path

**Files:**
- Create: `services/mlx-worker-python/worker/bootstrap.py`
- Create: `services/mlx-worker-python/worker/grpc_server.py`
- Create: `services/mlx-worker-python/worker/registry.py`
- Create: `services/mlx-worker-python/worker/runtime/mlx_text_runtime.py`
- Create: `services/mlx-worker-python/worker/engine/engine_core.py`
- Create: `services/mlx-worker-python/worker/engine/request_state.py`
- Create: `services/mlx-worker-python/worker/model_registry/catalog.py`
- Create: `services/mlx-worker-python/tests/test_runtime_service.py`
- Create: `services/mlx-worker-python/tests/test_generate_stream.py`
- Create: `services/mlx-worker-python/tests/test_abort.py`

**Step 1: Write the failing Python tests**

Add tests for:

- runtime handshake reports protocol version and capabilities
- `LoadModel` returns a model handle for one configured MLX text model
- `Generate` streams token events and a terminal completion event
- `Abort` stops an active generation and returns an explicit terminal error or cancelled completion
- unsupported RPCs return structured unimplemented errors

**Step 2: Run the Python tests and confirm they fail**

Run:

```bash
pytest services/mlx-worker-python/tests -q
```

Expected:

- failures because the gRPC server, runtime wrapper, and request tracking do not exist yet

**Step 3: Implement the worker vertical slice**

Implement:

- a gRPC-over-UDS server using generated worker protocol code
- `RuntimeService.Handshake`, `LoadModel`, `UnloadModel`, `GetRuntimeStats`, `ListLoadedModels`
- `InferenceService.Generate` and `Abort`
- a real MLX text runtime wrapper with deterministic configuration for one supported dev model
- active request bookkeeping so abort can cancel streaming generation safely

For this task:

- keep `Prefill`, `Decode`, `CacheService`, and `MaintenanceService` wired but explicitly unimplemented
- return zero-value cache stats and minimal capability reporting

**Step 4: Re-run the Python tests**

Run:

```bash
pytest services/mlx-worker-python/tests -q
```

Expected:

- runtime, generate, and abort tests pass

**Step 5: Commit**

```bash
git add services/mlx-worker-python
git commit -m "feat: add mlx worker text generation path"
```

### Task 4: Add the HTTP chat gateway, SSE streaming, and abort bridge

**Files:**
- Create: `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`
- Create: `services/control-plane-swift/Sources/HTTPGateway/SSE/SSEStreamWriter.swift`
- Create: `services/control-plane-swift/Sources/Requests/ChatRequestTranslator.swift`
- Create: `services/control-plane-swift/Sources/Requests/RequestCoordinator.swift`
- Create: `services/control-plane-swift/Sources/Requests/AbortRegistry.swift`
- Create: `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`
- Create: `services/control-plane-swift/Tests/HTTPGatewayTests/SSEStreamWriterTests.swift`
- Create: `services/control-plane-swift/Tests/HTTPGatewayTests/RequestCoordinatorTests.swift`

**Step 1: Write the failing Swift gateway tests**

Add tests for:

- `POST /v1/chat/completions` translates into a `Generate` worker request
- SSE emits content deltas in order and closes with a terminal event
- `GET /v1/models` returns loaded model state from the model catalog
- request cancellation triggers worker `Abort`

**Step 2: Run the targeted Swift tests and confirm they fail**

Run:

```bash
swift test --package-path services/control-plane-swift --filter HTTPGatewayTests
```

Expected:

- failures because the HTTP handlers and worker request bridge do not exist yet

**Step 3: Implement the minimal HTTP path**

Implement:

- a local HTTP listener with `POST /v1/chat/completions` and `GET /v1/models`
- chat request translation from HTTP shape into internal request identity plus worker `Generate`
- SSE streaming for token deltas, usage trailer, heartbeat, and terminal completion
- abort bridging from control plane request cancellation to worker `Abort`

Keep this phase intentionally narrow:

- no `responses`, `messages`, embeddings, rerank, images, or audio endpoints yet
- one active text request at a time
- FIFO request admission only

**Step 4: Re-run the targeted Swift tests**

Run:

```bash
swift test --package-path services/control-plane-swift --filter HTTPGatewayTests
```

Expected:

- HTTP translation, SSE, and abort bridge tests pass

**Step 5: Commit**

```bash
git add services/control-plane-swift
git commit -m "feat: add chat completions gateway and streaming"
```

### Task 5: Add the minimal menu bar shell and XPC client

**Files:**
- Create: `apps/macos-menubar/Sources/AppMain/AppMain.swift`
- Create: `apps/macos-menubar/Sources/MenuBar/StatusMenu.swift`
- Create: `apps/macos-menubar/Sources/Models/RuntimeViewModel.swift`
- Create: `apps/macos-menubar/Sources/XPCClient/ControlPlaneXPCClient.swift`
- Create: `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`
- Create: `apps/macos-menubar/Tests/MenuBarTests/ControlPlaneXPCClientTests.swift`

**Step 1: Write the failing menu bar tests**

Add tests for:

- handshake and snapshot hydration on app launch
- model list rendering from XPC snapshot data
- load/unload actions dispatch the correct control-plane commands
- event subscription updates runtime state in the view model

**Step 2: Run the app tests and confirm they fail**

Run:

```bash
swift test --package-path apps/macos-menubar
```

Expected:

- failures because the app package, XPC client, and view model do not exist yet

**Step 3: Implement the minimal operations shell**

Implement:

- app entry point and menu bar status surface
- XPC client using the generated control-plane protocol
- read-only runtime state rendering
- load/unload actions for the configured text model

Do not add:

- cache inspector
- settings persistence
- branch or request history UI
- direct worker access

**Step 4: Re-run the app tests**

Run:

```bash
swift test --package-path apps/macos-menubar
```

Expected:

- handshake, state hydration, and load/unload action tests pass

**Step 5: Commit**

```bash
git add apps/macos-menubar
git commit -m "feat: add minimal menu bar shell"
```

### Task 6: Add end-to-end integration and developer workflow validation

**Files:**
- Create: `tests/integration/test_chat_completions_stream.py`
- Create: `tests/integration/test_abort_flow.py`
- Create: `tests/integration/test_models_endpoint.py`
- Create: `scripts/dev_up.sh`
- Create: `scripts/dev_down.sh`

**Step 1: Write the failing integration tests**

Add tests for:

- booting one control plane and one worker locally
- loading a configured MLX text model
- `POST /v1/chat/completions` streams text deltas successfully
- abort cancels an in-flight request
- `GET /v1/models` reflects current loaded model state

**Step 2: Run the integration tests and confirm they fail**

Run:

```bash
pytest tests/integration -q
```

Expected:

- failures because the orchestration scripts and live services are not ready yet

**Step 3: Implement the integration harness**

Implement:

- dev scripts that launch the worker and control plane in the expected order
- integration fixtures for socket paths, model configuration, and health checks
- end-to-end assertions for streaming, abort, and model state

Ensure the scripts remain aligned with:

- `/var/run/melix/` socket layout
- one worker process for the initial slice
- deterministic local ports and cleanup behavior

**Step 4: Re-run the integration tests**

Run:

```bash
pytest tests/integration -q
make integration-test
```

Expected:

- the end-to-end streaming path passes locally

**Step 5: Commit**

```bash
git add tests/integration scripts
git commit -m "test: add first-slice integration coverage"
```

## Acceptance Criteria

The first implementation slice is complete when all of the following are true:

- `make proto` succeeds from a clean checkout
- the Swift daemon, Python worker, and menu bar app each build in isolation
- one configured MLX text model can be loaded through the control plane
- `POST /v1/chat/completions` streams content deltas through SSE
- `Abort` stops an active generation and leaves explicit terminal state
- `GET /v1/models` reflects load and unload state accurately
- the menu bar shell shows server and model state through XPC
- unsupported worker RPC surfaces return explicit unimplemented errors rather than silent failures

## Defaults and Assumptions

- This plan targets macOS on Apple Silicon only.
- The first live model path is a single real MLX text generation model, configured by a local development setting or fixed manifest, not by full user-facing model discovery.
- `docs/product-brief.md` remains intentionally ignored and untracked.
- Real `Prefill` and `Decode`, four-lane scheduling, session graph state, L2 cache persistence, snapshots, embeddings, rerank, and multimodal execution are deferred to the next implementation phase.
- Bun remains the default package manager for any future JavaScript surface, but no admin web work is included in this slice.
