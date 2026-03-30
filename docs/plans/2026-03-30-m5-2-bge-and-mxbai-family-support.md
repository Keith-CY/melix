# M5.2 BGE And MXBAI Family Support

## Goal

Add family-specific support for `bge` and `mxbai` style embedding models on top of the native embedding backend layer.

## Scope

- add family adapters and configuration rules
- preserve the generic embedding endpoint contract
- expose family capabilities through model registry metadata

## Files

- update `services/mlx-worker-python/worker/runtime/embedding_backends.py`
- update `services/mlx-worker-python/worker/runtime/deterministic_embedding_runtime.py`
- update `services/mlx-worker-python/worker/model_registry/catalog.py`
- update `services/mlx-worker-python/tests/test_embedding_runtime.py`
- update `tests/integration/test_non_text_endpoints.py`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift`
- update `services/control-plane-swift/Tests/ControlPlaneTests/ModelCatalogTests.swift`
- update `services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`

## Implementation Notes

- family adapters should own pooling and output-shape differences where they exist
- registry metadata should make family identity explicit to operators
- avoid embedding-family branching in the control plane
- BGE and MXBAI family adapters keep backend dispatch generic by translating family-specific prompt prefixes, pooling metadata, and dimensions inside the Python embedding layer
- the Swift control plane only forwards embedding metadata keys from catalog summaries into worker bootstrap specs, so family-specific behavior stays worker-owned

## Verification

- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_embedding_runtime.py -q`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest tests/integration/test_non_text_endpoints.py -q`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest tests/integration/test_runtime_core_acceptance.py -k runtime_core_keeps_text_embedding_and_rerank_models_warm_concurrently -q`
- `swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'phaseFiveSeedModelsExposeTypedCapabilitiesAndRoutes|bootstrapWorkerPreparationCarriesEmbeddingFamilyMetadataIntoWorkerModelSpecs'`
- changed-line coverage for touched Python files
- changed-line coverage for touched Swift files
- `git diff --check`

## Acceptance

- `bge` and `mxbai` style models can be registered and served through the embedding path
- family-specific behavior is test-covered

## Metrics Report

- Python verification: `services/mlx-worker-python/tests/test_embedding_runtime.py` -> `8 passed`
- Python verification: `tests/integration/test_non_text_endpoints.py` -> `7 passed`
- Runtime-core coexistence verification: `tests/integration/test_runtime_core_acceptance.py -k runtime_core_keeps_text_embedding_and_rerank_models_warm_concurrently` -> `1 passed`
- Swift verification: `swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'phaseFiveSeedModelsExposeTypedCapabilitiesAndRoutes|bootstrapWorkerPreparationCarriesEmbeddingFamilyMetadataIntoWorkerModelSpecs'` -> `2 passed`
- Python changed-line coverage: `96.20% (76/79)`
- Swift changed-line coverage: `100.00% (36/36)`
