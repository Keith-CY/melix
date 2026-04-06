# M8.1-M8.4 Backend Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the backend and control-plane foundations for `M8.1` through `M8.4` so Melix can discover models from ordered multi-root registries, derive structured provider or organization or variant identity, query Hugging Face metadata, and run resilient download workflows without depending on unfinished UI work.

**Architecture:** Keep the Python worker as the registry and model-operations execution authority, add explicit worker maintenance RPCs for registry and Hub workflows, and let the Swift control plane synchronize typed worker results into `ModelCatalog` and existing model-ops reply paths. Preserve the existing menu bar shell as a consumer of these backend surfaces rather than making UI code the source of truth.

**Tech Stack:** Swift 6, Swift Protobuf, Python 3.12, gRPC, XCTest, pytest, integration tests, repository-owned runbooks and metrics.

---

## Scope Notes

- This plan intentionally avoids net-new UI work in `apps/macos-menubar` beyond whatever compile-fixes or response-shape compatibility are strictly required after the `main` merge.
- Root, provider, organization, model, and variant identity should remain explicit and deterministic.
- Worker-maintained discovery and download state must remain machine-readable so later release gates and desktop surfaces can consume the same payloads.

## Performance Probes And Success Metrics

- `registry.reload_latency_ms`
- `registry.discovered_model_count`
- `registry.discovered_model_count_by_root`
- `hub.search_latency_ms`
- `download.resume_success_rate`
- `download.retry_count`
- `download.stall_detection_count`

## Task 1: M8.1 Ordered Multi-Root Registry

**Files:**
- Modify: `services/mlx-worker-python/worker/model_registry/catalog.py`
- Modify: `services/mlx-worker-python/worker/engine/maintenance_core.py`
- Modify: `services/mlx-worker-python/tests/test_model_registry_catalog.py`
- Modify: `services/mlx-worker-python/tests/test_maintenance_service.py`
- Modify: `services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/ModelCatalogTests.swift`
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
- Modify: `docs/architecture-spec.md`

- [x] Reuse the existing model-operations `registry_snapshot` manifest path for registry sync instead of adding a new worker-maintenance proto in this slice.
- [x] Write failing Python tests for ordered root parsing, duplicate suppression, invalid-root isolation, and registry snapshot serialization in `services/mlx-worker-python/tests/test_model_registry_catalog.py` and `services/mlx-worker-python/tests/test_maintenance_service.py`.
- [x] Write failing Swift tests for control-plane catalog synchronization and replacement sync behavior in `services/control-plane-swift/Tests/ControlPlaneTests/ModelCatalogTests.swift` and `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`.
- [x] Implement worker-side multi-root configuration parsing in `services/mlx-worker-python/worker/model_registry/catalog.py`, keeping root identity and root order explicit in model metadata.
- [x] Extend `registry_snapshot` manifests in `services/mlx-worker-python/worker/engine/maintenance_core.py` so worker-owned registry payloads flow through the existing model-operations path.
- [x] Implement `ModelCatalog` replacement sync and `ControlPlaneService` registry snapshot synchronization so the control plane can replace static discovery snapshots with worker-owned registry data without regressing existing seeded residency behavior.
- [x] Update `docs/architecture-spec.md` to record that model discovery now comes from an ordered worker registry rather than scattered single-path environment variables.
- [x] Run targeted verification:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_maintenance_service.py -q`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'syncRegistryModels'`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'executeHandlesModelListBySyncingRegistrySnapshotModelsFromTheModelOperationsWorker'`
- [x] Measure changed-line coverage for the touched Python and Swift scope and record the result for the Task 1 commit gate.
  - Python changed-line coverage: `100.00% (114/114)` via `services/mlx-worker-python/tests/test_model_registry_catalog.py` and `services/mlx-worker-python/tests/test_maintenance_service.py`.
  - Swift changed-line coverage: `99.67% (607/609)` via the targeted `ModelCatalogTests` and `ControlPlaneServiceTests` registry-sync cases.
- [x] Record the Task 1 metrics report for the changed scope.
  - Implemented probes in this slice: `registry.reload_latency_ms`, `registry.discovered_model_count`.
  - Runtime metrics capture: `N/A` in this worktree because verification used targeted unit tests and did not produce a long-running operator snapshot.
  - Deferred probe: `registry.discovered_model_count_by_root` is still listed for follow-up instrumentation in a later slice.
- [x] Commit Task 1:
  - `git add services/mlx-worker-python/worker/model_registry/catalog.py services/mlx-worker-python/worker/engine/maintenance_core.py services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_maintenance_service.py services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Tests/ControlPlaneTests/ModelCatalogTests.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift docs/architecture-spec.md docs/plans/2026-04-01-m8-1-m8-4-backend-foundations.md`
  - `git commit -m "feat: add ordered multi-root registry foundation"`

## Task 2: M8.2 Provider Or Org Or Model Or Variant Scanning

**Files:**
- Modify: `services/mlx-worker-python/worker/model_registry/catalog.py`
- Modify: `services/mlx-worker-python/tests/test_maintenance_service.py`
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/ModelCatalogTests.swift`
- Add: `services/control-plane-swift/Sources/ModelCatalog/RegistrySnapshotSync.swift`
- Modify: `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`
- Modify: `tests/integration/test_models_endpoint.py`
- Modify: `docs/runbooks/phase-8-local-install.md`

- [x] Write failing Python tests that create `provider/org/model/variant` directory trees with sidecar overrides and assert deterministic identity derivation, root-relative paths, and invalid-artifact skipping.
- [x] Write failing Swift tests that assert `ModelCatalog` preserves provider, organization, model, and variant identity from worker-owned metadata after synchronization.
- [x] Write or extend an integration test in `tests/integration/test_models_endpoint.py` so `/v1/models` exposes structured registry identity through the existing model metadata surface.
- [x] Implement structured tree scanning and sidecar override precedence in `services/mlx-worker-python/worker/model_registry/catalog.py`.
- [x] Ensure registry snapshots emitted through Task 1 include structured identity fields and do not collapse sibling variants into one flat record.
- [x] Update Swift catalog normalization and shared registry snapshot synchronization only as needed to keep the new identity metadata stable and observable.
- [x] Document the expected on-disk tree shape and rescan behavior in `docs/runbooks/phase-8-local-install.md`.
- [x] Run targeted verification:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_maintenance_service.py -q`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'ModelCatalogTests|getModelsSyncsRegistryModelsAndExposesStructuredRegistryIdentityMetadata'`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest tests/integration/test_models_endpoint.py -q`
- [x] Measure changed-line coverage for the touched Python and Swift scope and record the result for the Task 2 commit gate.
  - Python changed-line coverage: `99.10% (110/111)` across `catalog.py`, the registry unit tests, and the `/v1/models` integration test.
  - Swift changed-line coverage: `100.00% (229/229)` across the registry snapshot sync helper, HTTP model listing, and the touched test files.
- [x] Record the Task 2 metrics report for the changed scope.
  - Existing probes reused by this slice: `registry.reload_latency_ms`, `registry.discovered_model_count`.
  - Runtime metrics capture: `N/A` in this worktree because verification exercised identity propagation and endpoint rendering, not a sampled long-running operator session.
- [x] Commit Task 2:
  - `git add services/mlx-worker-python/worker/model_registry/catalog.py services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_maintenance_service.py services/control-plane-swift/Sources/ModelCatalog/RegistrySnapshotSync.swift services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Tests/ControlPlaneTests/ModelCatalogTests.swift services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift tests/integration/test_models_endpoint.py docs/runbooks/phase-8-local-install.md docs/plans/2026-04-01-m8-1-m8-4-backend-foundations.md`
  - `git commit -m "feat: add structured registry scanning identities"`

## Task 3: M8.3 Hugging Face Search, Pagination, And Model Cards

**Files:**
- Modify: `packages/protocol/schema/controlplane/v1/control_plane.proto`
- Modify: `packages/protocol/schema/worker/v1/maintenance.proto`
- Modify: `packages/protocol/descriptors/melix.pb`
- Create: `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- Modify: `services/mlx-worker-python/worker/control_plane_bridge.py`
- Modify: `services/mlx-worker-python/worker/grpc_server.py`
- Modify: `services/mlx-worker-python/worker/engine/maintenance_core.py`
- Modify: `services/mlx-worker-python/tests/test_control_plane_bridge_phase5.py`
- Modify: `services/mlx-worker-python/tests/test_maintenance_service.py`
- Modify: `services/control-plane-swift/Sources/WorkerClient/WorkerClient.swift`
- Modify: `services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
- Modify: `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`
- Modify: `services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/ControlPlaneXPCClientTests.swift`
- Modify: `docs/runbooks/phase-8-lora-adapter-workflow.md`

- [x] Add worker-maintenance request and reply messages for Hub search and Hub model-card fetch, add the matching control-plane ops request and reply surface, then regenerate protocol outputs with `make proto`.
- [x] Add failing Python tests for search pagination, cursor passthrough, MLX-only filtering, and normalized model-card payloads in `services/mlx-worker-python/tests/test_maintenance_service.py`.
- [x] Add failing bridge and control-plane tests that verify the new Hub requests are forwarded and that the control plane returns normalized search or card payloads without UI-owned parsing.
- [x] Implement a small Hub catalog client in `services/mlx-worker-python/worker/model_ops/hub_catalog.py`; use the Hugging Face `/api/models` HTTP endpoint directly so cursor pagination and `cardData=true` stay explicit without adding a new Python dependency.
- [x] Wire the new Hub catalog client through maintenance-core, gRPC service, and bridge entrypoints.
- [x] Add the matching Swift worker-client plumbing and control-plane request handling so existing UI code can consume stable backend responses after the `main` merge.
- [x] Update the relevant runbook with the new Hub discovery expectations and operator-visible filters.
- [x] Run targeted verification:
  - `make proto`
  - `UV_CACHE_DIR="$(pwd)/.uv-cache" uv sync --project services/mlx-worker-python`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_control_plane_bridge_phase5.py -q`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'executeHandlesOpsSearchHubModelsThroughTheModelOperationsWorker|executeHandlesOpsGetHubModelCardThroughTheModelOperationsWorker|executeReturnsUnavailableForHubOpsWithoutModelOperationsWorker|executeNormalizesWorkerDeclaredHubOpFailures|executeReturnsUnavailableWhenHubWorkerRequestsThrow|modelOpsBridgeMethodsDecodeHubSearchAndModelCardResponses'`
- [x] Measure changed-line coverage for the touched Python and Swift scope and record the result for the Task 3 commit gate.
  - Python changed-line coverage: `100.00% (41/41)` across `hub_catalog.py`, `control_plane_bridge.py`, `maintenance_core.py`, and `grpc_server.py`.
  - Swift changed-line coverage: `100.00% (123/123)` across `WorkerClient.swift`, `PythonBridgeWorkerClient.swift`, and `ControlPlaneService.swift`.
- [x] Record the Task 3 metrics report for the changed scope.
  - Implemented probe in this slice: `hub.search_latency_ms`.
  - Runtime metrics capture: `N/A` in this worktree because verification used targeted unit tests and bridge tests instead of a live operator session against Hugging Face.
  - Coverage gate note: generated protobuf outputs were regenerated with `make proto`; changed-line coverage was measured on the hand-written Python and Swift code paths above.
- [x] Record ancillary compatibility evidence for the touched desktop test stub.
  - `swift test --package-path apps/macos-menubar --filter ControlPlaneXPCClientTests` compiled `ControlPlaneXPCClientTests.swift` but the package still fails earlier on unrelated pre-existing Swift Testing macro type-check errors in `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`.
- [x] Commit Task 3:
  - `git add packages/protocol/schema/controlplane/v1/control_plane.proto packages/protocol/schema/worker/v1/maintenance.proto packages/protocol/descriptors/melix.pb packages/protocol/python packages/protocol/swift services/mlx-worker-python/worker/model_ops/hub_catalog.py services/mlx-worker-python/worker/control_plane_bridge.py services/mlx-worker-python/worker/grpc_server.py services/mlx-worker-python/worker/engine/maintenance_core.py services/mlx-worker-python/tests/test_control_plane_bridge_phase5.py services/mlx-worker-python/tests/test_maintenance_service.py services/control-plane-swift/Sources/WorkerClient/WorkerClient.swift services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift apps/macos-menubar/Tests/MenuBarTests/ControlPlaneXPCClientTests.swift docs/runbooks/phase-8-lora-adapter-workflow.md docs/plans/2026-04-01-m8-1-m8-4-backend-foundations.md`
  - `git commit -m "feat: add hub discovery search and model cards"`

## Task 4: M8.4 Resumable Downloads, Retries, Stalls, And Mirrors

**Files:**
- Create: `services/mlx-worker-python/worker/model_ops/download_pipeline.py`
- Modify: `services/mlx-worker-python/worker/model_ops/job_registry.py`
- Modify: `services/mlx-worker-python/worker/engine/maintenance_core.py`
- Modify: `services/mlx-worker-python/tests/test_maintenance_service.py`
- Modify: `services/mlx-worker-python/tests/test_control_plane_bridge_phase5.py`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
- Modify: `docs/runbooks/phase-8-local-install.md`
- Create: `scripts/m8_download_smoke.py`
- Modify: `services/mlx-worker-python/worker/productization/release_gates.py`
- Modify: `services/mlx-worker-python/worker/productization/acceptance_metrics.py`
- Modify: `services/mlx-worker-python/tests/test_release_gates.py`
- Modify: `services/mlx-worker-python/tests/test_runtime_edges.py`
- Modify: `services/mlx-text-worker-swift/Sources/Core/WorkerServices.swift`
- Modify: `services/mlx-text-worker-swift/Tests/CoreTests/WorkerScaffoldTests.swift`

Task 4 reused the Task 3 `convert_model` streaming manifest path, so no additional proto regeneration or `WorkerClient` transport changes were required in this slice after the `main` merge.

- [x] Add failing Python tests for partial-download resume, bounded retry behavior, stall classification, mirror override selection, and machine-readable progress manifests.
- [x] Add failing bridge and control-plane tests that verify download progress and terminal state are returned with the new fields instead of only a terminal artifact path.
- [x] Implement `services/mlx-worker-python/worker/model_ops/download_pipeline.py` with resumable state files, explicit retry bookkeeping, stall detection thresholds, and mirror selection sourced from request metadata.
- [x] Extend maintenance-core and job-registry so download jobs emit progress, resume metadata, retry counters, mirror identity, and stall reasons in a stable manifest.
- [x] Wire the new download reply shape through the existing worker bridge and control plane without regressing existing `upload`, `quantize`, `train_lora`, or `activate_adapter` flows.
- [x] Add a focused smoke script at `scripts/m8_download_smoke.py` and document its usage in `docs/runbooks/phase-8-local-install.md`.
- [x] Restore merged-main verification compatibility for the touched non-UI backend scope.
  - `services/mlx-worker-python/worker/productization/release_gates.py` now seeds a deterministic local training dataset and deterministic LoRA manifest path so productization evidence does not depend on a live MLX-LM training pipeline in tests.
  - `services/mlx-worker-python/worker/productization/acceptance_metrics.py` now reuses that deterministic training dataset path when seeding operator evidence.
  - `services/mlx-worker-python/tests/test_runtime_edges.py` now derives `MaintenanceService` method count from the protobuf descriptor instead of hard-coding the pre-Hub RPC count.
  - `services/mlx-text-worker-swift/Sources/Core/WorkerServices.swift` and `services/mlx-text-worker-swift/Tests/CoreTests/WorkerScaffoldTests.swift` now provide structured unimplemented stubs for the Hub maintenance RPCs introduced in Task 3 so `make swift-test` can continue past the text-worker package.
- [x] Run targeted verification:
  - `make proto`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_control_plane_bridge_phase5.py services/mlx-worker-python/tests/test_release_gates.py services/mlx-worker-python/tests/test_runtime_edges.py -q`
    - Result: `77 passed in 0.57s`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'executeHandlesModelRunOperationThroughTheModelOperationsWorker|executePreservesDownloadOperationStateWhenTheWorkerReturnsATerminalFailure|executeSurfacesWorkerSideFailuresForModelInfoAndOperations|executeSurfacesThrownModelInfoAndOperationWorkerErrors'`
    - Result: `4 tests passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path services/mlx-text-worker-swift --filter testMaintenanceRpcsReturnStructuredUnimplemented`
    - Result: `1 XCTest passed`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/m8_download_smoke.py --json`
    - Result: all smoke checks are `true` with `resume_from_bytes=1024`, `retry_count=2`, and `stall_reason=no_progress_timeout`.
- [x] Measure changed-line coverage for the touched Python and Swift scope and record the result for the Task 4 commit gate.
  - Python changed-line coverage: `98.02% (247/252)` across `download_pipeline.py`, `job_registry.py`, `maintenance_core.py`, `release_gates.py`, `acceptance_metrics.py`, and `scripts/m8_download_smoke.py`.
  - Swift changed-line coverage: `100.00% (20/20)` across `ControlPlaneService.swift` and `WorkerServices.swift`.
- [x] Record the Task 4 metrics report for the changed scope.
  - Implemented probes in this slice: `download.resume_success_rate`, `download.retry_count`, `download.stall_detection_count`.
  - Smoke evidence: `scripts/m8_download_smoke.py --json` produced a successful resume path, a two-retry recovery path, and a deterministic stall classification path without network access.
  - Runtime metrics capture: `N/A` in this worktree because validation is intentionally deterministic and local-file based rather than a long-running live mirror session.
- [x] Run broader verification for the full slice and record the actual outcome:
  - `make py-test`
    - Result: `323 passed in 1.12s`
  - `make swift-test`
    - Result: `packages/protocol/swift` and `services/mlx-text-worker-swift` completed, but the full `services/control-plane-swift` suite blocked again.
    - Fresh blocker evidence on `2026-04-02`: `swiftpm-testing-helper` for `services/control-plane-swift` sat at `0.0%` CPU until it was terminated; `/tmp/swiftpm-testing-helper_2026-04-02_0058_m84.sample.txt` shows the main thread idle in `CFRunLoopRun` and NIO threads waiting in `kevent`.
    - Prior matching evidence remains available at `/tmp/swiftpm-testing-helper_2026-04-02_004144_GGU4.sample.txt`.
- [x] Commit Task 4:
  - `git add services/mlx-worker-python/worker/model_ops/download_pipeline.py services/mlx-worker-python/worker/model_ops/job_registry.py services/mlx-worker-python/worker/engine/maintenance_core.py services/mlx-worker-python/worker/productization/release_gates.py services/mlx-worker-python/worker/productization/acceptance_metrics.py services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_control_plane_bridge_phase5.py services/mlx-worker-python/tests/test_release_gates.py services/mlx-worker-python/tests/test_runtime_edges.py services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift services/mlx-text-worker-swift/Sources/Core/WorkerServices.swift services/mlx-text-worker-swift/Tests/CoreTests/WorkerScaffoldTests.swift docs/runbooks/phase-8-local-install.md scripts/m8_download_smoke.py docs/plans/2026-04-01-m8-1-m8-4-backend-foundations.md`
  - `git commit -m "feat: add resilient model download workflows"`

## Final Verification And Handoff

- [x] Run the repository defaults for the touched slice:
  - `make proto`
    - Result: pass
  - `make py-test`
    - Result: `403 passed in 34.05s`
  - `make swift-test`
    - Result: pass
  - `make integration-test`
    - Result: `54 passed in 622.59s (0:10:22)`
- [x] Update `progress.md` and any milestone evidence docs needed to reflect what actually landed for `M8.1-M8.4`.
- [x] Produce a metrics report for the changed scope. If any probe is still `N/A`, record the reason explicitly in `progress.md` or the handoff note.
  - This close-out change is documentation-only, so executable changed-line coverage is `N/A`.
  - The committed M8.1-M8.4 tasks already recorded their task-level changed-line coverage inside this plan.
