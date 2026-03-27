# P1-M5 Control-Plane Swift Text Routing

**Goal:** Replace the control plane's single Python-backed text worker assumption with engine-aware routing that sends the default text path to the Swift text worker, while preserving the current HTTP and XPC surfaces and keeping failure behavior explicit.

**Scope:** This milestone covers the control-plane worker route model, a native Swift text worker client, bootstrap wiring for default text preload, and request dispatch selection for `/v1/chat/completions`. It does not add new public endpoints, silent fallback, non-text worker routing, or Phase 2 scheduler behavior.

## Context

- Canonical references:
  - `docs/architecture-spec.md`
  - `docs/worker-rpc-schema.md`
  - `docs/plans/2026-03-27-phase-1-swift-text-worker.md`
  - `docs/plans/2026-03-28-post-phase-0-coding-milestones.md`
  - `docs/plans/2026-03-28-p1-m4-swift-generate-abort.md`
- Current implementation state:
  - The Swift text worker can handshake, load models, stream `Generate`, and service `Abort`.
  - The control plane still hardcodes a single `PythonBridgeWorkerClient` for preload, `/v1/chat/completions`, and cancellation.
  - `ModelCatalog` only stores warmed model summaries and dispatch handles; it does not track which worker family owns a model.
  - The Phase 0 deterministic Python path remains useful for integration and comparison, but it is no longer the intended default text engine.
- Runtime dependency:
  - The Swift text worker exposes the shared worker RPC contract over gRPC on a Unix domain socket, which the control plane can reach directly.

## Non-Goals

- Silent fallback from the Swift text worker to the Python text path
- Prefill, decode, speculative execution, cache reuse, or queue lanes
- Routing for embeddings, rerank, image, audio, or maintenance workloads
- Desktop UI expansion
- New public endpoints or response shapes

## Assumptions

- `melix-dev-text` is the only default text model that must route to the Swift worker in this milestone.
- Python worker connectivity may still exist in the process for future non-text routing or comparison harnesses, but it is not used automatically for default text requests.
- Route selection can remain simple and deterministic in P1-M5: text models resolve to the Swift route, and missing or unhealthy routes fail with `worker_unavailable`.
- `MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH` remains the canonical socket override for the Swift text worker.

## Performance Probes

P1-M5 must define and record the first control-plane routing probes for the Swift route:

- `control_plane.worker_route_ms`
- `control_plane.worker_connect_ms`
- `control_plane.worker_preload_ms`

The milestone may keep end-to-end Swift-vs-Python comparison reporting for `P1-M6`, but probe availability is mandatory here.

## Work Plan

### Task 1: Introduce a route-aware worker model

**Objective**

Give the control plane a small route model that can select the correct worker client for the default text path without baking transport assumptions into request handling.

**Files**

- Modify: `services/control-plane-swift/Sources/WorkerClient/WorkerClient.swift`
- Create: `services/control-plane-swift/Sources/WorkerClient/WorkerRoute.swift`
- Create: `services/control-plane-swift/Sources/WorkerClient/WorkerRegistry.swift`
- Modify: `services/control-plane-swift/Sources/Requests/RequestCoordinator.swift`

**Implementation**

- Add a route abstraction that names worker families and the route they own.
- Add a worker registry that resolves the default text route by model ID and returns the correct worker client.
- Keep the first route table intentionally small: one Swift text route and optional compatibility routes for later work.
- Record route resolution latency in the metrics store.

**Acceptance**

- Request dispatch no longer depends on one globally injected worker client.
- Route lookup failure is explicit and testable.

### Task 2: Add a native Swift text worker client

**Objective**

Create a control-plane client that talks directly to the Swift text worker over the shared gRPC/UDS worker protocol.

**Files**

- Create: `services/control-plane-swift/Sources/WorkerClient/SwiftTextWorkerClient.swift`
- Modify: `services/control-plane-swift/Package.swift`
- Create tests under `services/control-plane-swift/Tests/WorkerClientTests/`

**Implementation**

- Implement the shared `WorkerClient` behavior using generated Swift gRPC stubs.
- Support `Handshake`, `LoadModel`, `Generate`, and `Abort` for the Phase 1 subset.
- Convert gRPC failures into `WorkerClientError.unavailable` so request handling keeps explicit failure semantics.
- Measure worker-connect or handshake latency through the metrics store or client-local timing hooks.

**Acceptance**

- The control plane can issue real Phase 1 worker RPCs to the Swift text worker without shelling out through the Python bridge.
- Worker-side transport failures surface as `worker_unavailable`.

### Task 3: Rewire bootstrap and preload for the Swift default text route

**Objective**

Make control-plane bootstrap warm the default text model through the Swift text worker and carry the resulting dispatch handle into the catalog.

**Files**

- Modify: `services/control-plane-swift/Sources/Bootstrap/main.swift`
- Modify: `services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift`
- Modify or extract: `services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift`

**Implementation**

- Build both the Swift text route and any non-default compatibility clients needed for later work.
- Preload `melix-dev-text` through the Swift client and record preload timing.
- Keep `ModelCatalog` authoritative for warmed state and dispatch handle, but allow route-aware bootstrap logic to set the correct handle.
- Do not silently retry the same model load through Python if the Swift route cannot load it.

**Acceptance**

- Bootstrap marks `melix-dev-text` warm only when the Swift route returns a real handle.
- `GET /v1/models` remains unchanged for clients but now reflects Swift-owned text readiness.

### Task 4: Lock behavior with red tests and control-plane verification

**Objective**

Use TDD to prove the routing switch before broad implementation and keep touched-scope coverage above the repository threshold.

**Files**

- Modify: `services/control-plane-swift/Tests/HTTPGatewayTests/RequestCoordinatorTests.swift`
- Modify: `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`
- Modify or create: `services/control-plane-swift/Tests/WorkerClientTests/*.swift`
- Modify: `docs/README.md`

**Implementation**

- Add failing tests first for:
  - request coordination using the resolved Swift text route rather than one global worker client
  - bootstrap preload recording a Swift-owned dispatch handle
  - explicit `worker_unavailable` when the Swift route is missing or unhealthy
  - `GET /v1/models` staying stable while backed by the Swift preload path
- Keep tests deterministic by using scripted worker clients or a small fake route registry instead of a live socket by default.
- Document one local control-plane plus Swift worker smoke command for later manual validation.

**Acceptance**

- The new routing tests fail before implementation and pass only after the routing change lands.
- Touched-scope automated coverage remains at or above `95%`.

## Verification

- `swift test --package-path services/control-plane-swift`
- `swift test --package-path services/control-plane-swift --filter WorkerClient`
- `swift test --package-path services/control-plane-swift --filter HTTPGateway`
- `swift test --package-path services/control-plane-swift --enable-code-coverage`
- `python3 scripts/swift_coverage_summary.py services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/MelixControlPlane.json /services/control-plane-swift/Sources/`
- `make swift-test`
- conditional local smoke with the Swift text worker socket and control-plane bootstrap

## Metrics Report Contract

P1-M5 must report:

- control-plane worker-client test time
- touched-scope Swift source coverage for the control-plane package
- probe availability for route, connect, and preload timing
- local Swift-route smoke result or explicit `N/A` reason when no worker socket is configured

## Rollback / Safe Exit

- If the native Swift worker transport proves unstable, the milestone may still land with the route registry, bootstrap wiring, deterministic route tests, and a feature-gated Swift client that fails explicitly when disabled. It must not revert to silent Python fallback for the default text path.
