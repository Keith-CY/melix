# M11.1 Disk Streaming Mode And Runtime Flags

## Status

Completed on 2026-04-05 with a repository-owned disk-streaming mode enum, worker-facing runtime
flags, explicit typed unsupported-runtime failures, and operator-visible requested-versus-effective
disk-streaming state across control-plane snapshots and the native desktop shell.

## Goal

Define the runtime-facing disk-streaming mode and the typed flags or settings needed to enable it safely.

## Scope

- add disk-streaming mode to runtime settings
- carry session-level streaming flags through control-plane state
- keep mode visibility explicit for operators

## Files

- update `packages/protocol/schema/controlplane/v1/`
- update `packages/protocol/schema/worker/v1/`
- update `services/control-plane-swift/Sources/`
- update `services/control-plane-swift/Tests/`
- update `services/mlx-text-worker-swift/Sources/Core/`
- update `services/mlx-text-worker-swift/Tests/CoreTests/`
- update `services/mlx-worker-python/worker/`
- update `services/mlx-worker-python/tests/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `apps/macos-menubar/Tests/MenuBarTests/`

## Implementation Notes

- Disk streaming remains an explicit operator choice or policy outcome instead of an inferred
  free-form setting.
- Mode flags stay compatible with residency summaries, runtime-session state, and worker load
  requests.
- Unsupported runtime paths fail explicitly with typed `disk_streaming_unsupported` errors instead
  of silently ignoring the requested mode.
- The native desktop shell exposes both requested and effective disk-streaming state so operators
  can tell whether a model stayed resident or was rejected before entering a streaming path.

## Verification

- `make proto`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_runtime_service.py services/mlx-worker-python/tests/test_runtime_edges.py -q`
- `make py-test`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/mlx-text-worker-swift --scratch-path /tmp/m11_1_text_cov --enable-code-coverage --filter WorkerScaffoldTests`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --scratch-path /tmp/m11_1_cp_cov --enable-code-coverage --filter 'ControlPlaneServiceTests|OnDemandModelLoaderTests|ModelCatalogTests|PythonBridgeWorkerClientTests'`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --scratch-path /tmp/m11_1_menu_cov --enable-code-coverage --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|DesktopShellStateTests'`
- `make swift-test`
- `make integration-test`
- `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/m11_1_python_coverage.json services/mlx-worker-python/worker/grpc_server.py services/mlx-worker-python/worker/registry.py services/mlx-worker-python/tests/test_runtime_service.py services/mlx-worker-python/tests/test_runtime_edges.py`
- `python3 scripts/swift_changed_line_coverage.py --binary /tmp/m11_1_text_cov/arm64-apple-macosx/debug/MelixTextWorkerSwiftPackageTests.xctest/Contents/MacOS/MelixTextWorkerSwiftPackageTests --profdata /tmp/m11_1_text_cov/arm64-apple-macosx/debug/codecov/default.profdata services/mlx-text-worker-swift/Sources/Core/WorkerRuntimeRegistry.swift services/mlx-text-worker-swift/Sources/Core/WorkerServices.swift services/mlx-text-worker-swift/Tests/CoreTests/WorkerScaffoldTests.swift`
- `python3 scripts/swift_changed_line_coverage.py --binary /tmp/m11_1_cp_cov/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata /tmp/m11_1_cp_cov/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift services/control-plane-swift/Sources/Snapshots/ServerSessionRuntimeStore.swift services/control-plane-swift/Sources/WorkerClient/OnDemandModelLoader.swift services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift services/control-plane-swift/Tests/WorkerClientTests/OnDemandModelLoaderTests.swift services/control-plane-swift/Tests/ControlPlaneTests/ModelCatalogTests.swift services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`
- `python3 scripts/swift_changed_line_coverage.py --binary /tmp/m11_1_menu_cov/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata /tmp/m11_1_menu_cov/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift apps/macos-menubar/Sources/AppMain/Models/DesktopShellState.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift`
- `git diff --check`

## Acceptance

- Disk-streaming mode is represented consistently across protocol, control plane, and runtime settings.
- Unsupported runtime paths fail explicitly with typed `disk_streaming_unsupported` errors instead
  of silently downgrading the requested mode.
- Operator-facing model settings, runtime-session detail, and residency summaries expose requested
  versus effective disk-streaming state without decoding free-form metadata.

## Verification Results

- `make proto`: pass
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_runtime_service.py services/mlx-worker-python/tests/test_runtime_edges.py -q`: `31 passed in 0.20s`
- `make py-test`: `456 passed in 34.49s`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/mlx-text-worker-swift --scratch-path /tmp/m11_1_text_cov --enable-code-coverage --filter WorkerScaffoldTests`: `133 tests in 1 suite passed after 1.391 seconds`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --scratch-path /tmp/m11_1_cp_cov --enable-code-coverage --filter 'ControlPlaneServiceTests|OnDemandModelLoaderTests|ModelCatalogTests|PythonBridgeWorkerClientTests'`: pass
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --scratch-path /tmp/m11_1_menu_cov --enable-code-coverage --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|DesktopShellStateTests'`: `173 tests in 3 suites passed after 3.453 seconds`
- `make swift-test`: pass
- `make integration-test`: `60 passed in 734.45s (0:12:14)`

## Metrics Report

- typed disk-streaming control-plane or operator counters in the touched scope:
  - `control_plane.server_runtime_session_count`
  - `menu.model_settings_ms`
  - `menu.server_snapshot_ms`
- changed-line coverage for the touched executable scope:
  - Python worker runtime scope: `96.97%` (`32/33`)
  - Swift text worker scope: `100.00%` (`164/164`)
  - Swift control-plane scope: `99.67%` (`305/306`)
  - Swift menu bar scope: `96.53%` (`139/144`)
  - aggregate changed-line coverage across the touched handwritten executable scope: `98.92%` (`640/647`)
- protocol schemas, generated protobuf outputs, `packages/protocol/descriptors/melix.pb`, and
  task-planning documents are excluded from executable changed-line coverage because they are
  generated or repository-ownership artifacts rather than handwritten runtime logic.
