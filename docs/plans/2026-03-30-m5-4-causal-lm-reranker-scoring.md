# M5.4 Causal-LM Reranker Scoring

## Goal

Add causal-LM reranker support, including yes-no logit scoring, without forking the shared rerank API surface.

## Scope

- introduce causal-LM rerank scoring
- add yes-no logit scoring semantics
- preserve the shared rerank request and response contract

## Files

- update `services/mlx-worker-python/worker/runtime/rerank_backends.py`
- update `services/mlx-worker-python/worker/model_registry/catalog.py`
- update `services/mlx-worker-python/tests/test_rerank_runtime.py`
- update `tests/integration/test_non_text_endpoints.py`
- update `services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift`
- update `services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift`
- update `services/control-plane-swift/Tests/ControlPlaneTests/ModelCatalogTests.swift`
- update `services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`

## Implementation Notes

- scoring adapters should separate family-specific prompt and scoring logic from the endpoint contract
- registry metadata should declare when yes-no scoring is in effect
- keep rerank metrics comparable across architecture families
- keep the default development reranker on `jina-v3`
- allow full-stack rerank testing to switch families through `MELIX_DEV_RERANK_FAMILY_ID`
- carry `rerank_yes_no_labels` through the Swift preload path so `/v1/rerank` stays contract-compatible across families

## Verification

- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_rerank_runtime.py -k 'causal_lm or yes_no_metadata' -q`
  - `2 passed, 10 deselected in 0.07s`
- `swift test --package-path services/control-plane-swift --filter 'devRerankModelReadsCausalLMEnvironmentOverrides|bootstrapWorkerPreparationCarriesCausalLMRerankMetadataIntoWorkerModelSpecs'`
  - `2 tests in 2 suites passed`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest tests/integration/test_non_text_endpoints.py -k causal_lm_yes_no_scoring -q`
  - `1 passed, 8 deselected in 11.94s`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_rerank_runtime.py -q`
  - `12 passed in 0.06s`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest tests/integration/test_non_text_endpoints.py -k rerank_endpoint -q`
  - `3 passed, 6 deselected in 41.09s`
- `swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'phaseFiveSeedModelsExposeTypedCapabilitiesAndRoutes|phaseFivePreloadWritesEmbeddingAndRerankHandlesIntoTheModelCatalog|devRerankModelReadsCausalLMEnvironmentOverrides|bootstrapWorkerPreparationCarriesCausalLMRerankMetadataIntoWorkerModelSpecs'`
  - `4 tests in 2 suites passed`
- `PYTHONPATH=.:services/mlx-worker-python COVERAGE_FILE=/tmp/m5_4_python.coverage uv run --project services/mlx-worker-python coverage run --source=services/mlx-worker-python/worker,tests/integration -m pytest services/mlx-worker-python/tests/test_rerank_runtime.py tests/integration/test_non_text_endpoints.py tests/integration/test_runtime_core_acceptance.py -q`
  - `23 passed in 142.83s`
- `git diff --check`
  - passed

## Metrics

- Python changed-line coverage: `100.00% (42/42)`
- Swift changed-line coverage: `97.22% (70/72)`
- Combined changed-line coverage for the touched scope remains above the repository `95%` gate
- Uncovered Swift branches:
  - `ModelCatalog.swift:356` (`basic` family default scoring path)
  - `PythonBridgeWorkerClient.swift:514` (catalog miss fallback path)

## Acceptance

- causal-LM rerank models can score and rank documents through the shared rerank path
- yes-no scoring behavior is explicitly test-covered
- shared `/v1/rerank` remains compatible across `jina-v3` and `causal-lm` family metadata
