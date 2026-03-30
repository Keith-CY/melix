# M4.8 Vision Model-Family Adapters

## Goal

Add family adapters for broader vision-model support without baking family-specific behavior directly into the generic VLM runtime.

## Scope

- define adapter boundaries for vision-model families
- keep shared multimodal semantics above family-specific runtime details
- expose family capabilities and constraints to operators

## Files

- update `services/mlx-worker-python/worker/runtime/deterministic_vlm_runtime.py`
- add `services/mlx-worker-python/worker/runtime/vision_family_adapters.py`
- update `services/mlx-worker-python/worker/model_registry/catalog.py`
- update `services/mlx-worker-python/tests/test_vision_runtime.py`
- update `tests/integration/test_vlm_phase_aware_lifecycle.py`
- update `services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift`
- update `services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift`
- update `services/control-plane-swift/Tests/ControlPlaneTests/ModelCatalogTests.swift`
- update `services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`

## Implementation Notes

- adapters should own family-specific tokenization, prompt shaping, and capability declarations
- registry metadata should explain modality and task support clearly
- avoid a monolithic VLM runtime file that absorbs every family difference
- add a dedicated adapter module that resolves family defaults into a runtime-facing config
- seed `llava-v1` as the default Melix VLM family and add a single-image `paligemma-v1` path to prove adapter selection
- keep shared prompt rendering, cache accounting, and phase-aware lifecycle in the generic VLM runtime
- surface family metadata through both Python model specs and Swift control-plane summaries so worker bootstrap does not drop operator-declared constraints

## Verification

- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_vision_runtime.py -k 'family or paligemma or invalid_family' -q`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_vision_runtime.py tests/integration/test_vlm_phase_aware_lifecycle.py -q`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest tests/integration/test_vlm_phase_aware_lifecycle.py -k family_specific_prompt_defaults -q`
- `swift test --package-path services/control-plane-swift --filter 'phaseSixContractSeedModelsExposeMultimodalRoutesAndTasks|bootstrapWorkerPreparationCarriesOCRProfileMetadataIntoWorkerModelSpecs|bootstrapWorkerPreparationCarriesVLMFamilyMetadataIntoWorkerModelSpecs'`
- `PYTHONPATH=.:services/mlx-worker-python COVERAGE_FILE=/tmp/m4_8_python.coverage uv run --project services/mlx-worker-python coverage run --source=services/mlx-worker-python/worker,tests/integration -m pytest services/mlx-worker-python/tests/test_vision_runtime.py tests/integration/test_vlm_phase_aware_lifecycle.py -k 'not supports_phase_aware_prefill_and_decode' -q`
- `PYTHONPATH=.:services/mlx-worker-python COVERAGE_FILE=/tmp/m4_8_python.coverage uv run --project services/mlx-worker-python coverage json -o /tmp/m4_8_python_coverage.json`
- `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/m4_8_python_coverage.json services/mlx-worker-python/worker/model_registry/catalog.py services/mlx-worker-python/worker/runtime/deterministic_vlm_runtime.py services/mlx-worker-python/worker/runtime/vision_family_adapters.py services/mlx-worker-python/tests/test_vision_runtime.py tests/integration/test_vlm_phase_aware_lifecycle.py`
- `swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'phaseSixContractSeedModelsExposeMultimodalRoutesAndTasks|bootstrapWorkerPreparationCarriesOCRProfileMetadataIntoWorkerModelSpecs|bootstrapWorkerPreparationCarriesVLMFamilyMetadataIntoWorkerModelSpecs'`
- `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift services/control-plane-swift/Tests/ControlPlaneTests/ModelCatalogTests.swift services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`

## Acceptance

- broader vision-model families can be integrated through adapter boundaries
- capability declarations and integration behavior remain test-covered

## Metrics Report

- Python changed-line coverage: `100.00% (132/132)`
- Swift changed-line coverage: `100.00% (44/44)`
- Python runtime and integration verification: `29 passed`, plus targeted family integration `1 passed`
