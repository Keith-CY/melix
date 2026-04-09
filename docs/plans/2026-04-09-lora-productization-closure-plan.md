# LoRA Productization Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close all remaining LoRA product gaps in Melix, including QLoRA, derived-model lifecycle, evaluation comparison, and acceptance evidence, using `mlx-community/Qwen3.5-0.8B-OptiQ-4bit` as the fixed acceptance model.

**Architecture:** Keep the existing `RunModelOperation` and evaluation orchestration surfaces intact, then extend worker manifests, control-plane snapshot syncing, CLI command plumbing, and Window UI state so LoRA workflows behave as one end-to-end product. Use small TDD slices: Python worker truth first, Swift orchestration second, operator surfaces third, and acceptance harnesses last.

**Tech Stack:** Python, Swift, SwiftUI, protobuf-generated contracts, MLX/MLX-LM, pytest, Swift Testing, repository-owned smoke scripts.

**Window UI Execution Mode:** Production UI calls the public `melix` subprocess. Tests call the same
CLI runner seam directly so positive and negative UI coverage stays deterministic.

**Integration Workflow:** After each completed phase, squash-merge the phase branch into local
`main`, then start the next phase from the updated `main`.

---

## Phase Boundaries

- Phase 1: Acceptance baseline plus worker training closure
- Phase 2: Derived-model lifecycle plus control-plane catalog closure
- Phase 3: CLI and evaluation compare closure
- Phase 4: Window UI, E2E, acceptance evidence, coverage, and metrics closure

## Phase 1 Status

Status on 2026-04-09: completed and ready for phase-exit squash merge into local `main`.

Verification evidence:

- Targeted worker tests: `35 passed`
- Changed-scope worker coverage for `training_config.py`, `training_dataset.py`, and
  `lora_training_pipeline.py`: `98%`
- CLI acceptance slice: `swift test --filter MelixCLIRunnerTests` -> `51 tests passed`
- Window UI acceptance slice:
  `swift test --package-path apps/macos-menubar --filter DesktopPolishSmokeTests` ->
  `1 test passed`

Metrics report:

- `N/A` for a dedicated LoRA closure metrics command in Phase 1. This phase closes request
  validation, dataset materialization, manifest persistence, and acceptance-fixture pinning. The
  repository-owned LoRA product metrics command is scheduled in Task 8.

## Phase 2 Status

Status on 2026-04-09: completed and ready for phase-exit squash merge into local `main`.

Verification evidence:

- Targeted worker lifecycle tests:
  `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_maintenance_service.py -q`
  -> `99 passed in 34.64s`
- Targeted Swift lifecycle and catalog suites:
  `swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'PythonBridgeWorkerClientTests|ControlPlaneServiceTests|ModelCatalogTests'`
  -> `267 tests in 3 suites passed`
- Changed-scope Python coverage for `adapter_activation_pipeline.py`, `job_registry.py`, and
  `maintenance_core.py`: `96%`
- Changed-line Swift spot checks confirm the new lines in `ModelCatalog.swift`,
  `RegistrySnapshotSync.swift`, and `ControlPlaneService.swift` all executed at least once in the
  Phase 2 verification suite, including `source_model_revision`, `activation_mode`,
  `adapter_manifest_path`, `remove_supported`, adapter-backed catalog registration, and
  remove-derived catalog pruning.

Metrics report:

- `N/A` for a dedicated Phase 2 LoRA lifecycle metrics command. This phase closes worker removal
  orchestration, registry snapshot hydration, and control-plane catalog correctness. The
  repository-owned LoRA product metrics command is still scheduled in Task 8.

## File Map

### Worker and productization

- Modify: `services/mlx-worker-python/worker/model_ops/training_config.py`
- Modify: `services/mlx-worker-python/worker/model_ops/training_dataset.py`
- Modify: `services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py`
- Modify: `services/mlx-worker-python/worker/model_ops/adapter_activation_pipeline.py`
- Modify: `services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py`
- Modify: `services/mlx-worker-python/worker/model_ops/job_registry.py`
- Modify: `services/mlx-worker-python/worker/engine/maintenance_core.py`
- Modify: `services/mlx-worker-python/worker/engine/evaluation_core.py`
- Add: `services/mlx-worker-python/worker/productization/evaluation_compare.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_schemas.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_store.py`
- Add or modify: `services/mlx-worker-python/worker/productization/evaluation_reports.py`

### Worker tests

- Modify: `services/mlx-worker-python/tests/test_lora_model_ops.py`
- Modify: `services/mlx-worker-python/tests/test_maintenance_service.py`
- Modify: `services/mlx-worker-python/tests/test_evaluation_core.py`
- Modify: `services/mlx-worker-python/tests/test_evaluation_schemas.py`
- Modify: `services/mlx-worker-python/tests/test_evaluation_store.py`

### Swift control plane and CLI

- Modify: `Sources/MelixCLICore/MelixCLI.swift`
- Modify: `services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift`
- Modify: `services/control-plane-swift/Sources/ModelCatalog/RegistrySnapshotSync.swift`
- Modify: `services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`

### Swift tests

- Modify: `Tests/MelixCLITests/MelixCLIParserTests.swift`
- Modify: `Tests/MelixCLITests/MelixCLIRunnerTests.swift`
- Modify: `services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/ModelCatalogTests.swift`

### Window UI

- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`

### Window UI tests

- Modify: `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/DesktopPolishSmokeTests.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/OperatorSessionPersistenceSmokeTests.swift`

### Docs and runbooks

- Modify: `docs/runbooks/phase-8-lora-adapter-workflow.md`
- Modify: `docs/runbooks/benchmark-matrix-evaluation-and-lora.md`
- Modify: `docs/runbooks/phase-8-product-acceptance.md`
- Modify: `docs/plans/2026-04-01-real-lora-closed-loop.md`
- Modify: `docs/plans/2026-04-07-multimodal-evaluation-and-lora-comparison-roadmap.md`

## Task 1: Acceptance Baseline Consolidation

**Files:**
- Modify: `docs/runbooks/phase-8-lora-adapter-workflow.md`
- Modify: `docs/runbooks/benchmark-matrix-evaluation-and-lora.md`
- Modify: `docs/runbooks/phase-8-product-acceptance.md`
- Modify: `Tests/MelixCLITests/MelixCLIRunnerTests.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/DesktopPolishSmokeTests.swift`

- [x] Write failing tests that expect the fixed acceptance model repo ID to appear in LoRA acceptance outputs and smoke fixtures.
- [x] Run the targeted CLI and Window UI tests to verify the current fixtures still point at legacy dev-model identities and fail the new expectation.
- [x] Update smoke fixtures, acceptance helpers, and runbooks to pin `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`.
- [x] Re-run the targeted tests to verify the acceptance baseline is stable.

Verification commands:

- `swift test --filter MelixCLIRunnerTests`
- `swift test --package-path apps/macos-menubar --filter DesktopPolishSmokeTests`
- Phase exit action: squash-merge the completed phase branch into local `main`

## Task 2: QLoRA and Validation-Split Worker Support

**Files:**
- Modify: `services/mlx-worker-python/worker/model_ops/training_config.py`
- Modify: `services/mlx-worker-python/worker/model_ops/training_dataset.py`
- Modify: `services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py`
- Modify: `services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py`
- Modify: `services/mlx-worker-python/tests/test_lora_model_ops.py`

- [x] Write failing positive and negative pytest cases for `training_mode=qlora`, `hf_valid_split`, unsupported validation combinations, and desired derived-model alias persistence.
- [x] Run `pytest services/mlx-worker-python/tests/test_lora_model_ops.py -q` and verify the new cases fail for the right reason.
- [x] Implement config normalization for QLoRA and validation split handling with typed errors for unsupported families or missing validation inputs.
- [x] Extend normalized dataset snapshots and adapter manifests to preserve validation strategy, validation split, quantization mode, and desired derived-model alias.
- [x] Re-run the targeted pytest file and keep the slice green.

Verification commands:

- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_lora_model_ops.py -q`
- Phase exit action: squash-merge the completed phase branch into local `main`

## Task 3: Activation Modes and Remove-Derived Lifecycle

**Files:**
- Modify: `services/mlx-worker-python/worker/model_ops/adapter_activation_pipeline.py`
- Modify: `services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py`
- Modify: `services/mlx-worker-python/worker/engine/maintenance_core.py`
- Modify: `services/mlx-worker-python/worker/model_ops/job_registry.py`
- Modify: `services/mlx-worker-python/tests/test_lora_model_ops.py`
- Modify: `services/mlx-worker-python/tests/test_maintenance_service.py`

- [x] Write failing positive and negative pytest coverage for `adapter_backed_runtime`, `remove_derived_model`, invalid activation mode, and missing derived targets.
- [x] Run the targeted pytest files and verify the failures are caused by missing lifecycle support rather than broken fixtures.
- [x] Implement adapter-backed activation manifests, lifecycle artifacts, and removal orchestration that unloads, deletes product-owned artifacts, and refreshes registry state.
- [x] Persist the new lifecycle metadata into registry snapshots and make repeated or invalid removal attempts fail with typed errors.
- [x] Re-run the targeted worker tests until the lifecycle slice is green.

Verification commands:

- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_maintenance_service.py -q`

## Task 4: Control-Plane Snapshot and Catalog Closure

**Files:**
- Modify: `services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift`
- Modify: `services/control-plane-swift/Sources/ModelCatalog/RegistrySnapshotSync.swift`
- Modify: `services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/ModelCatalogTests.swift`

- [x] Write failing Swift tests for adapter-backed derived models, remove-derived orchestration, and snapshot hydration of the new metadata.
- [x] Run the targeted Swift tests to verify the new expectations fail against the current snapshot sync path.
- [x] Implement control-plane request forwarding, derived-summary hydration, catalog refresh, and adapter-aware load behavior for both activation modes.
- [x] Re-run the targeted Swift test groups and keep them passing before moving on.

Verification commands:

- `swift test --package-path services/control-plane-swift --filter PythonBridgeWorkerClientTests`
- `swift test --package-path services/control-plane-swift --filter ControlPlaneServiceTests`
- `swift test --package-path services/control-plane-swift --filter ModelCatalogTests`
- Phase exit action: squash-merge the completed phase branch into local `main`

## Task 5: CLI Surface Completion

**Files:**
- Modify: `Sources/MelixCLICore/MelixCLI.swift`
- Modify: `Tests/MelixCLITests/MelixCLIParserTests.swift`
- Modify: `Tests/MelixCLITests/MelixCLIRunnerTests.swift`

- [ ] Write failing parser and runner tests for `--training-mode qlora`, `--hf-valid-split`, `--activation-mode adapter_backed_runtime`, `lora remove-derived`, and `eval compare`.
- [ ] Run the targeted CLI test files and verify the failures are feature gaps rather than parser mistakes.
- [ ] Implement parser, options models, client dispatch, and human-readable output for the new LoRA lifecycle and compare commands.
- [ ] Re-run the targeted CLI tests and keep JSON and text output stable.

Verification commands:

- `swift test --filter MelixCLIParserTests`
- `swift test --filter MelixCLIRunnerTests`

## Task 6: Evaluation Compare Worker Path

**Files:**
- Modify: `services/mlx-worker-python/worker/engine/evaluation_core.py`
- Add: `services/mlx-worker-python/worker/productization/evaluation_compare.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_schemas.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_store.py`
- Add or modify: `services/mlx-worker-python/worker/productization/evaluation_reports.py`
- Modify: `services/mlx-worker-python/tests/test_evaluation_core.py`
- Modify: `services/mlx-worker-python/tests/test_evaluation_schemas.py`
- Modify: `services/mlx-worker-python/tests/test_evaluation_store.py`

- [ ] Write failing positive and negative pytest coverage for compare-job validation, paired sample persistence, regression counting, and export generation.
- [ ] Run the targeted evaluation pytest files and verify the failures reflect missing compare support.
- [ ] Implement serial compare execution over one fixed suite bundle and one frozen control set, then persist deltas, paired rows, win/loss/tie counts, regression counts, and report bundles.
- [ ] Re-run the targeted evaluation tests and keep export formats deterministic.

Verification commands:

- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_evaluation_schemas.py services/mlx-worker-python/tests/test_evaluation_store.py -q`
- Phase exit action: squash-merge the completed phase branch into local `main`

## Task 7: Window UI Workflow Closure

**Files:**
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/DesktopPolishSmokeTests.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/OperatorSessionPersistenceSmokeTests.swift`

- [ ] Write failing Window UI tests for QLoRA controls, validation split wiring, activation mode selection, remove-derived actions, and compare-job initiation.
- [ ] Run the targeted MenuBar test suites and verify the failures are caused by missing bindings and view state.
- [ ] Implement the Window UI state, action routing, and visible status rendering for the new LoRA lifecycle and comparison flows.
- [ ] Re-run the targeted MenuBar tests and keep the existing desktop product patterns intact.

Verification commands:

- `swift test --package-path apps/macos-menubar --filter RuntimeViewModelTests`
- `swift test --package-path apps/macos-menubar --filter DesktopFoundationViewTests`
- `swift test --package-path apps/macos-menubar --filter DesktopPolishSmokeTests`
- `swift test --package-path apps/macos-menubar --filter OperatorSessionPersistenceSmokeTests`

## Task 8: Acceptance, E2E, Coverage, and Metrics Closure

**Files:**
- Modify: `docs/runbooks/phase-8-lora-adapter-workflow.md`
- Modify: `docs/runbooks/benchmark-matrix-evaluation-and-lora.md`
- Modify: `docs/runbooks/phase-8-product-acceptance.md`
- Modify any repository-owned smoke scripts required by the new CLI and Window UI coverage

- [ ] Add or update repository-owned E2E or smoke flows that exercise train, activate, compare, export, and remove-derived using `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`.
- [ ] Run the targeted smoke coverage first, then the full repository gates.
- [ ] Capture the changed-scope coverage report and confirm the touched scope stays at or above 95 percent or document the measurable gap and add the missing coverage command.
- [ ] Produce the changed-scope metrics report and refresh acceptance evidence references in the English runbooks.

Verification commands:

- `make proto`
- `make py-test`
- `make swift-test`
- `make integration-test`
- `make coverage`
- `make phase8-metrics PHASE8_METRICS_ARGS="--json"`
- Phase exit action: squash-merge the completed phase branch into local `main`

## Self-Review Checklist

- [ ] Every design requirement from `docs/plans/2026-04-09-lora-productization-closure-design.md` maps to at least one task above.
- [ ] No task relies on `TODO`, `TBD`, or implied test coverage.
- [ ] Every new LoRA capability has both positive and negative test coverage plus an end-to-end acceptance path.
- [ ] The fixed acceptance model remains `mlx-community/Qwen3.5-0.8B-OptiQ-4bit` in code, smoke fixtures, and runbooks.
