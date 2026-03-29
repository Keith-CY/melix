# P8-M2 Diagnostics, Bench, and LoRA Training Workflows

## Goal

Turn the Phase 8 diagnostics and training placeholders into real operator workflows. This milestone adds deterministic doctor and bench execution, introduces a first `train_lora` model-ops path, and exposes the workflows through the native desktop tools surface.

## Scope

- Python maintenance worker support for `RunDoctor`, `RunBench`, and `train_lora`
- Swift control-plane routing for `ops.run_doctor` and `ops.run_bench`
- native desktop tools actions and result hydration for doctor, bench, and LoRA training
- deterministic tests and measurable metrics for the new operator workflows

## Non-Goals

- packaging, signing, launchd, installer, or release-asset work
- full QLoRA orchestration or long-running distributed training
- HuggingFace upload automation beyond the existing model-operation substrate
- benchmark gating and release policy changes that belong to later Phase 8 milestones

## Files

- Modify: `services/mlx-worker-python/worker/engine/maintenance_core.py`
- Modify: `services/mlx-worker-python/worker/control_plane_bridge.py`
- Modify: `services/mlx-worker-python/tests/test_maintenance_service.py`
- Modify: `services/mlx-worker-python/tests/test_runtime_edges.py`
- Modify: `services/mlx-worker-python/tests/test_control_plane_bridge_phase5.py`
- Modify: `services/control-plane-swift/Sources/WorkerClient/WorkerClient.swift`
- Modify: `services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift`
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Modify: `services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/XPCClient/ControlPlaneXPCClient.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/ControlPlaneXPCClientTests.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift`
- Modify: `docs/README.md`

## Desired Behavior

- `RunDoctor` returns a deterministic markdown report instead of an `unimplemented` error.
- `RunBench` streams structured start, progress, metric, and completion events and writes a deterministic markdown report.
- `train_lora` is accepted as a model operation, emits manifest and artifact output, and remains visible through existing model-ops result surfaces.
- The native desktop tools tab exposes buttons for doctor, bench, and LoRA training and renders the most recent results.
- Control-plane metrics record doctor, bench, and training latency for the touched operator paths.

## Performance Probes

- `control_plane.ops_doctor_ms`
- `control_plane.ops_bench_ms`
- `menu.ops_doctor_ms`
- `menu.ops_bench_ms`
- `menu.model_operation_ms`
- `training.job_duration_ms`
- `training.adapter_publish_ms`

## Test Plan

- Add failing Python maintenance tests for deterministic doctor, bench, and `train_lora`.
- Add failing bridge tests for `run-doctor` and `run-bench`.
- Add failing Swift worker-client and control-plane tests for the new ops paths.
- Add failing app tests for desktop tools actions and result hydration.
- Run:
  - `make swift-test`
  - `make py-test`
  - `make integration-test`
  - `make coverage`
  - `git diff --check`

## Acceptance

- Doctor and bench are no longer placeholder workflows.
- A first LoRA training path exists as a deterministic, operator-visible model operation.
- The desktop tools surface exposes and verifies the new workflows.
- Touched-scope coverage remains at or above `95%`.
