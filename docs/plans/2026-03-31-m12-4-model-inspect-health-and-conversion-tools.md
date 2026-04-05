# M12.4 Model Inspect, Health, And Conversion Tools

## Goal

Expose model inspection, health checking, and conversion tooling as stable operator workflows tied to model metadata.

## Scope

- add typed inspect-model output and structured health-check reporting
- add conversion and quantized packaging entrypoints with stable result metadata
- keep tools visible through model and tools surfaces

## Execution Status

- Completed:
  - typed inspect-model output with stable backend, family, source, workflow-role, revision, and
    supported-task metadata across the worker, control plane, and Window UI
  - structured doctor health output with typed `healthy`, `warning`, `degraded`, and `failed`
    states plus actionable findings projected through the control plane and operator shell
- In progress:
  - conversion and quantized packaging entrypoints with stable artifact, manifest, and
    verification metadata

## Files

- update `packages/protocol/schema/controlplane/v1/`
- update `packages/protocol/schema/worker/v1/`
- update `services/mlx-worker-python/worker/model_ops/`
- update `services/mlx-worker-python/worker/engine/`
- update `services/control-plane-swift/Sources/WorkerClient/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `apps/macos-menubar/Sources/AppMain/`

## Implementation Notes

- Inspection payloads should remain typed and machine-readable.
- Health checks should report actionable `healthy`, `warning`, `degraded`, and `failed` states
  instead of generic markdown-only output.
- Conversion should remain a model-ops job with explicit result metadata.

## Verification

- first executable slice verification:
  - `make proto`
  - `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python --extra mlx coverage run --data-file=/tmp/m12_4_python.coverage -m pytest services/mlx-worker-python/tests/test_maintenance_service.py -q`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'ControlPlaneServiceTests|PythonBridgeWorkerClientTests'`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'ControlPlaneXPCClientTests|RuntimeViewModelTests|DesktopFoundationViewTests'`
  - changed-line coverage:
    - Python worker inspect or doctor scope: `100.00%` (`103/103`)
    - Swift control-plane scope: `100.00%` (`117/117`)
    - Swift menu-bar scope: `100.00%` (`186/186`)
- `make py-test`
- `make swift-test`
- `make integration-test`

## Acceptance

- Inspect, health, and conversion tools are operator-visible and test-covered.
- Tool results remain tied to stable model identity and manifests.
