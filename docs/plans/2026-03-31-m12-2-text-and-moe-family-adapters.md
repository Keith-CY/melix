# M12.2 Text And MoE Family Adapters

## Goal

Add the text-family and MoE-family adapter coverage needed for expanded large-model compatibility.

## Status

Completed. Melix now discovers, annotates, routes, and verifies the targeted dense and MoE text
families through repository-owned worker metadata, control-plane catalog summaries, and live-path
integration evidence.

## Scope

- add family adapters for larger text and MoE-oriented models
- carry family-specific capability declarations into routing
- keep adapter behavior testable and metadata-driven

## Files

- update `services/mlx-worker-python/worker/runtime/`
- update `services/mlx-worker-python/worker/model_registry/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `tests/integration/`

## Implementation Notes

- Family-specific attention, positional-encoding, and MoE behaviors should remain adapter-scoped.
- Capability metadata should drive routing and settings affordances.
- Unsupported subfamilies should fail explicitly instead of degrading silently.
- The base dev text seed remains on `swift_text`; larger dense and MoE families route through
  `python_text_compatibility`.
- The repository-owned support matrix now includes text-family contract declarations plus
  live-path evidence for the targeted family rows.

## Verification

- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_text_family_adapters.py services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_mlx_backend.py services/mlx-worker-python/tests/test_acceptance_metrics.py -q`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest tests/integration/test_text_family_endpoints.py tests/integration/test_non_text_endpoints.py::test_family_support_matrix_tracks_live_verified_family_overrides -q`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'ModelCatalogTests|ControlPlaneServiceTests|PythonBridgeWorkerClientTests'`
- `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/m12_2_python_coverage.json services/mlx-worker-python/worker/runtime/text_family_adapters.py services/mlx-worker-python/worker/model_registry/catalog.py services/mlx-worker-python/worker/runtime/mlx_text_runtime.py services/mlx-worker-python/worker/productization/family_support_matrix.py services/mlx-worker-python/tests/test_text_family_adapters.py services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_mlx_backend.py services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_text_family_endpoints.py tests/integration/test_non_text_endpoints.py`
- `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift services/control-plane-swift/Tests/ControlPlaneTests/ModelCatalogTests.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
- `git diff --check`

## Acceptance

- Expanded text and MoE families can be scanned, loaded, and routed through adapter metadata.
- Integration checks cover the targeted family matrix.
- The support matrix reports `6` text families, with live-path verification for `llama`,
  `mistral4`, `qwen3moe`, `deepseek-mla`, and `nemotron-h`, while `mixtral` remains explicitly
  `contract_only`.
