# M17.1 Speech-To-Text Backend Adapters And Model Matrix

## Status

Completed on 2026-04-06. The repository now exposes `Whisper`-class and `Parakeet`-class
speech-to-text families across the Swift control-plane catalog, the Python bridge model-spec path,
and the repository-owned model-family support matrix, with focused Swift, Python, and integration
evidence recorded in-repo.

## Goal

Add real speech-to-text backend families to Melix with typed capability metadata, routing rules, and a stable compatibility matrix.

## Scope

- add `Whisper`-class and `Parakeet`-class backend adapters
- expose backend capabilities and model metadata
- add routing and compatibility checks for supported transcription models

## Files

- update `services/mlx-worker-python/worker/runtime/`
- update `services/mlx-worker-python/worker/model_registry/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `tests/integration/`

## Implementation Notes

- Backend-specific assumptions about chunking, timestamps, and language detection should remain adapter-local.
- Capability metadata must remain stable enough for both operator surfaces and API consumers.

## Verification

- `make py-test`
- `make swift-test`
- `make integration-test`
- `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_audio_runtime.py services/mlx-worker-python/tests/test_mlx_audio_runtime.py services/mlx-worker-python/tests/test_runtime_edges.py services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_non_text_endpoints.py -q`
- `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python coverage run --data-file=/tmp/m17_1_python.coverage -m pytest services/mlx-worker-python/tests/test_audio_runtime.py services/mlx-worker-python/tests/test_mlx_audio_runtime.py services/mlx-worker-python/tests/test_runtime_edges.py services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_non_text_endpoints.py -q`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'ModelCatalogTests|PythonBridgeWorkerClientTests'`
- `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift services/control-plane-swift/Tests/ControlPlaneTests/ModelCatalogTests.swift services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`

## Acceptance

- Real speech-to-text backend families are discoverable, routable, and test-covered.
- Model metadata distinguishes backend family and supported transcription capabilities.
