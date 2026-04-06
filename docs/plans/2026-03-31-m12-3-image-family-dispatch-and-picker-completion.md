# M12.3 Image Family Dispatch And Picker Completion

## Goal

Complete image-family dispatch and picker visibility for the supported creative model families.

Status: completed. Image-family detection is now repository-owned across the Python worker,
control-plane catalog sync, the family support matrix, and the Window UI picker, with role-aware
generation-versus-edit filtering and typed request validation for unsupported workflows.

## Scope

- add class-based dispatch for supported image families
- expose picker metadata for generation and editing roles
- keep family support operator-visible in the product shell

## Files

- update `services/mlx-worker-python/worker/runtime/`
- update `services/mlx-worker-python/worker/model_registry/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `apps/macos-menubar/Sources/AppMain/Image/`

## Implementation Notes

- Dispatch should use stable family classes rather than regex-only naming logic.
- Picker state should remain grounded in capability metadata.
- Family-specific constraints should stay discoverable in operator-visible metadata.

## Verification

- `make py-test`
- `make swift-test`
- `make integration-test`
- `PYTHONPATH=services/mlx-worker-python uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_image_family_adapters.py services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_image_runtime.py services/mlx-worker-python/tests/test_acceptance_metrics.py services/mlx-worker-python/tests/test_runtime_service.py tests/integration/test_image_endpoints.py tests/integration/test_non_text_endpoints.py::test_family_support_matrix_tracks_live_verified_family_overrides -q`
- `swift test --package-path services/control-plane-swift --filter 'ModelCatalogTests|PythonBridgeWorkerClientTests'`
- `swift test --package-path apps/macos-menubar --filter RuntimeViewModelTests`

## Acceptance

- Supported image families dispatch through the correct runtime class.
- Picker coverage for those families is complete and test-covered.
