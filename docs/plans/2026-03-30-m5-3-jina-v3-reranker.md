# M5.3 Jina V3 Reranker

## Goal

Add a Jina v3 reranker path that uses family-specific scoring behavior while preserving the shared rerank API contract.

## Scope

- introduce Jina-family rerank scoring
- preserve the generic rerank response shape
- expose family identity and capability through model metadata

## Files

- add `services/mlx-worker-python/worker/runtime/rerank_backends.py`
- update `services/mlx-worker-python/worker/runtime/deterministic_rerank_runtime.py`
- update `services/mlx-worker-python/worker/model_registry/catalog.py`
- update `services/mlx-worker-python/tests/test_rerank_runtime.py`
- update `tests/integration/test_non_text_endpoints.py`
- update `services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift`
- update `services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift`
- update `services/control-plane-swift/Tests/ControlPlaneTests/ModelCatalogTests.swift`
- update `services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`

## Implementation Notes

- scoring logic should remain isolated from the generic rerank API surface
- registry metadata should make Jina-family support explicit
- later family additions should reuse the same adapter pattern
- Jina v3 rerank scoring is implemented as a family adapter on top of a deterministic token-overlap backend so later families can plug in without changing the shared rerank response contract
- the control plane only seeds and forwards rerank metadata keys; family-specific scoring remains worker-owned
- the Jina family uses order-aware overlap bonuses so exact query-order matches outrank word-shuffled documents while preserving deterministic tie-breaking

## Verification

- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_rerank_runtime.py -q`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest tests/integration/test_non_text_endpoints.py -k rerank_endpoint -q`
- `PYTHONPATH=.:services/mlx-worker-python COVERAGE_FILE=/tmp/m5_3_python.coverage uv run --project services/mlx-worker-python coverage run --source=services/mlx-worker-python/worker,tests/integration -m pytest services/mlx-worker-python/tests/test_rerank_runtime.py tests/integration/test_non_text_endpoints.py tests/integration/test_runtime_core_acceptance.py -q`
- `swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'phaseFiveSeedModelsExposeTypedCapabilitiesAndRoutes|bootstrapWorkerPreparationCarriesRerankFamilyMetadataIntoWorkerModelSpecs'`
- changed-line coverage for touched Python files
- changed-line coverage for touched Swift files
- `git diff --check`

## Acceptance

- Jina-family rerank models can serve through the shared rerank endpoint
- scoring behavior and top-k semantics are test-covered

## Metrics Report

- Python verification: `services/mlx-worker-python/tests/test_rerank_runtime.py` -> `10 passed`
- Rerank endpoint verification: `tests/integration/test_non_text_endpoints.py -k rerank_endpoint` -> `2 passed`
- Combined Python coverage run: `services/mlx-worker-python/tests/test_rerank_runtime.py + tests/integration/test_non_text_endpoints.py + tests/integration/test_runtime_core_acceptance.py` -> `20 passed`
- Swift verification: `swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'phaseFiveSeedModelsExposeTypedCapabilitiesAndRoutes|bootstrapWorkerPreparationCarriesRerankFamilyMetadataIntoWorkerModelSpecs'` -> `2 passed`
- Python changed-line coverage: `100.00% (119/119)`
- Swift changed-line coverage: `100.00% (27/27)`
