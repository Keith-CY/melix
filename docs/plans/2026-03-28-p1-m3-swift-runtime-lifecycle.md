# P1-M3 Swift Text Runtime Lifecycle

**Goal:** Replace the P1-M2 lifecycle placeholders with a real Swift-side text runtime lifecycle for the development text model, including model source resolution, load, unload, list, and runtime stats, while keeping `Generate` deferred to P1-M4.

**Scope:** This milestone covers the Swift worker model catalog, runtime backend abstraction, the first real Swift MLX load path, resident-memory accounting, runtime lifecycle metrics, and the runtime RPC behavior for `LoadModel`, `UnloadModel`, `ListLoadedModels`, and `GetRuntimeStats`. It does not implement token generation, prompt rendering for live inference, or control-plane routing changes.

## Context

- Canonical references:
  - `docs/architecture-spec.md`
  - `docs/worker-rpc-schema.md`
  - `docs/plans/2026-03-27-phase-1-swift-text-worker.md`
  - `docs/plans/2026-03-28-post-phase-0-coding-milestones.md`
  - `docs/plans/2026-03-28-p1-m2-swift-text-worker-scaffold.md`
- Current implementation state:
  - `services/mlx-text-worker-swift/` exists and satisfies the shared worker RPC surface with scaffold behavior.
  - `LoadModel` and `UnloadModel` still return structured `unimplemented`.
  - `ListLoadedModels` and `GetRuntimeStats` only reflect an empty placeholder registry.
  - The Python worker already has a development model catalog and a load/unload lifecycle pattern worth mirroring at the behavior level.
- External runtime dependency:
  - The official `mlx-swift-lm` package exposes the `MLXLMCommon` library and a simplified async `loadModel(id:)` API for loading local or Hugging Face model sources.
  - This milestone should use that Swift-native load path for real runtime lifecycle behavior.

## Non-Goals

- Real `Generate` or token streaming
- Real `Abort` behavior beyond preserving the existing scaffold
- Prefill, decode, speculative execution, cache reuse, or snapshots
- Control-plane worker routing changes
- Desktop or operator workflow changes beyond the plan and metrics updates required for this milestone

## Assumptions

- The default development model remains `melix-dev-text`.
- `MELIX_DEV_TEXT_MODEL_PATH` remains the environment override for the development text model source and may point to either a local path or a Hugging Face model identifier.
- Unit tests must not depend on a live MLX runtime or an actual downloaded model; lifecycle tests should use injected fake backends.
- Live MLX smoke verification is expected to be conditional on a real configured model source and available Swift MLX runtime dependencies.
- Resident-memory accounting may use process-level measurement and should prefer a conservative estimate over a fabricated exact model size.

## Performance Probes

P1-M3 must define and record the first lifecycle probes for the Swift text worker:

- `swift_text.load_model_ms`
- `swift_text.unload_model_ms`
- `swift_text.runtime_stats_ms`
- `swift_text.peak_resident_bytes`
- `swift_text.loaded_model_count`

This milestone does not need TTFT or token-throughput data yet, but it must leave the metrics surface ready for P1-M4.

## Work Plan

### Task 1: Add runtime lifecycle primitives

**Objective**

Introduce the internal types needed to manage resolved model specs, runtime-loaded model objects, and resident-memory accounting.

**Files**

- Create: `services/mlx-text-worker-swift/Sources/Core/Models/WorkerModelCatalog.swift`
- Create: `services/mlx-text-worker-swift/Sources/Core/Runtime/TextRuntime.swift`
- Create: `services/mlx-text-worker-swift/Sources/Core/Runtime/SwiftMLXBackend.swift`
- Modify: `services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift`
- Modify: `services/mlx-text-worker-swift/Sources/Core/MetricsStore.swift`

**Implementation**

- Add a Swift model catalog mirroring the Phase 0 development model contract and `MELIX_DEV_TEXT_MODEL_PATH` override semantics.
- Add a runtime backend protocol so tests can inject fake lifecycle behavior while the live worker uses a Swift-native MLX load path.
- Add resident-memory probing that can record process-level memory before and after model load.
- Extend the runtime registry to own:
  - loaded model handles
  - resolved model specs
  - runtime-loaded model state
  - estimated resident bytes
  - active loaded-model count

**Acceptance**

- The registry can resolve, load, unload, and list development models without inference support.
- Resident-memory stats are coherent and testable.

### Task 2: Implement runtime RPC lifecycle behavior

**Objective**

Replace the scaffold `unimplemented` behavior for `LoadModel` and `UnloadModel` with real lifecycle behavior while preserving explicit failure states.

**Files**

- Modify: `services/mlx-text-worker-swift/Sources/Core/WorkerServices.swift`
- Modify: `services/mlx-text-worker-swift/Sources/Core/WorkerConfiguration.swift`
- Modify: `services/mlx-text-worker-swift/Sources/Core/WorkerBootstrap.swift`

**Implementation**

- Make `LoadModel`:
  - resolve the requested model spec through the Swift model catalog
  - load the model through the runtime backend
  - assign a stable worker-local handle
  - record lifecycle metrics and resident-memory estimates
  - return resolved capabilities and the allocated handle
- Make `UnloadModel`:
  - remove the loaded handle from the registry
  - update resident-memory accounting
  - return `not_found` only when the model handle is unknown
- Keep `WarmupModel` explicitly `unimplemented` in this milestone.
- Keep `Handshake`, `ListLoadedModels`, and `GetRuntimeStats` consistent with the real registry state.

**Acceptance**

- Runtime RPCs report real lifecycle state transitions.
- Unknown handles return explicit `not_found`.
- Failed loads return explicit `load_failed`.

### Task 3: Add lifecycle-focused tests and smoke path

**Objective**

Use TDD to lock the lifecycle contract before implementation and keep the package coverage above the repository threshold.

**Files**

- Modify or create tests under `services/mlx-text-worker-swift/Tests/CoreTests/`
- Modify: `Makefile` only if a new verification entrypoint becomes necessary
- Modify: `docs/README.md`

**Implementation**

- Add failing tests first for:
  - development model path override resolution
  - successful load and handle allocation
  - unload and missing-handle behavior
  - runtime stats reflecting loaded-model resident bytes
  - `load_failed` propagation on backend failure
  - lifecycle metrics recording
- Keep unit tests backend-injected and deterministic.
- Add or document one manual live MLX smoke command for a configured `MELIX_DEV_TEXT_MODEL_PATH`.

**Acceptance**

- The new worker tests drive the runtime lifecycle behavior instead of just the scaffold behavior.
- Touched-scope automated coverage remains at or above `95%`.

## Verification

- `swift test --package-path services/mlx-text-worker-swift`
- `swift test --package-path services/mlx-text-worker-swift --enable-code-coverage`
- `python3 scripts/swift_coverage_summary.py services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/codecov/MelixTextWorkerSwift.json /services/mlx-text-worker-swift/Sources/`
- `make swift-test`
- conditional manual live smoke with a configured `MELIX_DEV_TEXT_MODEL_PATH`

## Metrics Report Contract

P1-M3 must report:

- Swift text worker lifecycle test time
- touched-scope Swift source coverage
- load-model and unload-model probe availability
- live MLX smoke result or explicit `N/A` reason when no model source is configured

## Rollback / Safe Exit

- If the live MLX backend dependency proves unstable, the milestone may still land with the runtime backend protocol, model catalog, and deterministic fake-backed lifecycle tests, but the RPC surface must remain ready for a real Swift MLX backend to drop in without changing the service contract.
