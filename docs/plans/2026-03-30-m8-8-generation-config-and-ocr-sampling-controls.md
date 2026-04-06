# M8.8 Generation Config And OCR Sampling Controls

Status: completed in commit `feat: close M8.8 generation config and OCR sampling controls`

## Goal

Import generation-config defaults where available and expose OCR-specific sampling controls without fragmenting the shared settings model.

## Scope

- load and merge generation-config defaults
- expose OCR-specific sampling controls
- preserve explicit override precedence

## Files

- update `services/mlx-worker-python/worker/model_registry/catalog.py`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `tests/integration/`

## Implementation Notes

- generation-config import should remain non-destructive and inspectable
- OCR sampling controls should integrate with the shared settings model rather than bypass it
- keep precedence rules explicit and testable

## Verification

- `make py-test`
- `make swift-test`
- `make integration-test`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_model_registry_catalog.py -q`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'TextEndpointContractTests|PythonBridgeWorkerClientTests'`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`
- `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/m8_8_python_coverage.json services/mlx-worker-python/worker/model_registry/catalog.py services/mlx-worker-python/tests/test_model_registry_catalog.py`
- `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift services/control-plane-swift/Sources/Requests/ChatRequestTranslator.swift services/control-plane-swift/Sources/Requests/TextRequestShaper.swift services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Tests/ControlPlaneTests/TextEndpointContractTests.swift services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`
- `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift`

## Acceptance

- generation-config defaults can be loaded and merged
- OCR sampling controls are operator-visible and test-covered

## Completion Notes

- registry discovery now imports `generation_config.json` into inspectable `melix.generation_config.*` metadata without overwriting explicit manifest values, and malformed or non-mapping sidecars remain non-destructive no-ops
- control-plane request shaping now applies imported generation-config defaults through a shared `ModelSamplingPolicy`, while OCR execution policy falls back to those defaults only when OCR-specific overrides are absent
- the native operator shell now exposes OCR sampling profile, temperature, top-p, and max-token controls in the existing model-settings form and surfaces imported generation-config provenance plus effective OCR defaults in the model info summary
- changed-line coverage for the touched executable scope:
  - Python worker: `100.00% (86/86)`
  - control plane: `98.00% (196/200)`
  - menu bar: `97.90% (280/286)`
