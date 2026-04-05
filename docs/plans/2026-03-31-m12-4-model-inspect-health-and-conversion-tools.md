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
  - conversion and quantized packaging entrypoints with stable artifact, manifest, and
    verification metadata, including dedicated conversion bundles, upload receipts, and
    operator-visible summary state for runtime compatibility and source artifact provenance

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
- second executable slice verification:
  - `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_maintenance_service.py -q`
  - `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python --extra mlx coverage run --data-file=/tmp/m12_4_convert_python.coverage -m pytest services/mlx-worker-python/tests/test_maintenance_service.py -q && PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python --extra mlx coverage json --data-file=/tmp/m12_4_convert_python.coverage -o /tmp/m12_4_convert_python_coverage.json && python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/m12_4_convert_python_coverage.json services/mlx-worker-python/worker/model_ops/conversion_pipeline.py services/mlx-worker-python/worker/model_ops/upload_receipt_pipeline.py services/mlx-worker-python/worker/engine/maintenance_core.py services/mlx-worker-python/tests/test_maintenance_service.py`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'DesktopFoundationViewTests'`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`
  - `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`
  - changed-line coverage:
    - Python worker conversion or packaging scope: `95.49%` (`254/266`)
    - Swift menu-bar conversion or packaging scope: `98.88%` (`353/357`)
- `make py-test`
- `make swift-test`
- `make integration-test`

## Acceptance

- Inspect, health, and conversion tools are operator-visible and test-covered.
- Tool results remain tied to stable model identity and manifests.
