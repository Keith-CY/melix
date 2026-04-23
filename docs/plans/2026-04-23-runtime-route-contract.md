# Runtime Route Contract Remediation

## Goal

Make model runtime routing explicit and shared across registry sync, Chat, LoRA-derived models,
model load, and benchmark execution. The control plane must not infer a Python runtime solely from
`model_kind: "text"`; text describes model capability, not the worker backend.

## Context

PR #56 exposed a routing-contract gap through two Swift CI failures in
`ControlPlaneServiceTests`: legacy registry snapshots with `model_kind: "text"` and no
`melix.capability.route_kind` stopped reaching the default text worker. The regression came from
mapping bare text registry entries to `python_text_compatibility` during registry snapshot parsing.

Existing plans already define the intended contract:

- `2026-03-28-p5-m1-capability-and-settings-model.md`: route selection should resolve from typed
  model metadata rather than ad-hoc naming.
- `2026-04-01-m8-1-m8-4-backend-foundations.md`: the Python worker is the registry and
  model-operations execution authority; Swift synchronizes typed worker results.
- `2026-03-31-m12-2-text-and-moe-family-adapters.md`: larger dense and MoE text families route
  through explicit Python compatibility metadata while the base dev text seed remains `swift_text`.
- `2026-04-21-lora-adapter-backed-runtime.md`: derived models carry typed runtime metadata and
  preserve adapter-backed execution identity.

## Contract

- `model_kind` is capability-oriented. Bare `text` means the model can generate text; it does not
  select Swift or Python execution by itself.
- Explicit route metadata wins:
  - typed `route_class`, when present;
  - `melix.capability.route_kind`, including the legacy alias `python_text_compatibility`;
  - derived-model metadata that declares its source route.
- Registry snapshot parsing preserves explicit route metadata and otherwise leaves routing to the
  shared resolver. It must not silently reinterpret `text` as a Python backend.
- Legacy text snapshots without route metadata fall back to the default text route for compatibility.
  Worker-owned rescans should emit explicit route metadata for Python-compatible managed models.
- LoRA-derived models inherit the source model route unless their activation manifest declares a
  more specific route.
- Chat, model load, and benchmark execution must resolve through the same catalog/worker-registry
  projection so selecting a server model cannot produce different runtime behavior across surfaces.

## Implementation Steps

- [x] Add Swift regression coverage for legacy text snapshots without route metadata:
  `model.load` and `ops.run_bench` must continue to reach their default text/model-ops workers after
  registry sync.
- [x] Add Swift coverage for explicit Python compatibility registry snapshots:
  Chat/model load should select the Python compatibility route only when route metadata says so.
- [x] Add or keep derived-model coverage showing adapter-backed/derived entries inherit or preserve
  explicit route metadata instead of falling back from `model_kind`.
- [x] Update `RegistrySnapshotSync` so bare `text` maps to the default text route, while explicit
  `python_text_compatibility` and `python_compatibility` metadata still normalize to the Python
  compatibility route.
- [x] Ensure `WorkerRegistry` remains the single route-resolution source for execution surfaces.
- [x] Update the macOS UI follow-up plan to remove the obsolete assumption that older managed text
  manifests without route metadata should default to Python compatibility.

## Verification

- `swift test --package-path services/control-plane-swift --filter 'executeHandlesModelListBySyncingRegistrySnapshotModelsFromTheModelOperationsWorker|executeSyncsRegistryModelsBeforeWorkerBackedModelLoad|executeSyncsRegistryModelsBeforeRunBenchResolution|startChatSyncsManagedRegistryModelsBeforeLazyLoad|registrySnapshotTextFamiliesPreserveCompatibilityRoutingAndParserMetadata|WorkerRegistryTests'`
- `swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'executeHandlesModelListBySyncingRegistrySnapshotModelsFromTheModelOperationsWorker|executeSyncsRegistryModelsBeforeWorkerBackedModelLoad|executeSyncsRegistryModelsBeforeRunBenchResolution|startChatSyncsManagedRegistryModelsBeforeLazyLoad|registrySnapshotTextFamiliesPreserveCompatibilityRoutingAndParserMetadata|executeImportsDirectHFBenchmarkTargetForGemma4|WorkerRegistryTests|ModelCatalogTests'`
- `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift services/control-plane-swift/Sources/ModelCatalog/RegistrySnapshotSync.swift services/control-plane-swift/Sources/WorkerClient/WorkerRegistry.swift services/control-plane-swift/Sources/WorkerClient/WorkerRoute.swift services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift services/control-plane-swift/Tests/WorkerClientTests/WorkerRegistryTests.swift`
- `swift test --package-path services/control-plane-swift`
- `git diff --check`

## Metrics

- Runtime throughput metrics: `N/A`; this slice changes routing metadata and deterministic
  dispatch, not inference hot-path performance.
- Existing registry probes remain relevant: `registry.reload_latency_ms` and
  `registry.discovered_model_count`.
- Changed-line coverage: `100.00% (134/134)` for the touched Swift scope.
- Success metric: route-resolution regressions are covered by focused Swift tests and PR CI should
  no longer fail the registry sync cases after this branch is pushed.
