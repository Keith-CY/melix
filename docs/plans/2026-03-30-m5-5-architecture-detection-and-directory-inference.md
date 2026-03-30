# M5.5 Architecture Detection And Directory Inference

## Goal

Add architecture detection and directory-level inference so model-family routing stops depending on manual hardcoded registration.

## Scope

- infer architecture and family from model metadata and directory structure
- preserve explicit overrides where needed
- keep detection results visible to operators and diagnostics

## Files

- update `services/mlx-worker-python/worker/model_registry/catalog.py`
- update `services/mlx-worker-python/worker/engine/maintenance_core.py`
- update `services/mlx-worker-python/tests/test_embedding_runtime.py`
- update `services/mlx-worker-python/tests/test_rerank_runtime.py`
- update `services/mlx-worker-python/tests/test_maintenance_service.py`
- update `tests/integration/test_non_text_endpoints.py`
- update `services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift`
- update `services/control-plane-swift/Tests/ControlPlaneTests/ModelCatalogTests.swift`

## Implementation Notes

- detection now prefers explicit override keys and falls back to directory-name heuristics for development model paths
- overrides must remain possible for ambiguous or incomplete artifacts
- diagnostics expose both detected and effective identity through model ext metadata and `RunDoctor`
- embedding inference covers `bert`, `xlmr`, `bge-m3`, and `mxbai-embed`
- rerank inference covers `basic`, `jina-v3`, and `causal-lm`

## Verification

- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_embedding_runtime.py -k 'directory_name or override_is_applied' -q`
  - `2 passed, 9 deselected in 0.10s`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_rerank_runtime.py -k 'directory_name or override_is_applied' -q`
  - `2 passed, 12 deselected in 0.10s`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_maintenance_service.py -k 'detected_and_overridden_model_identity' -q`
  - `1 passed, 8 deselected in 0.11s`
- `swift test --package-path services/control-plane-swift --filter 'devEmbeddingModelInfersMXBaiIdentityFromDirectoryName|devRerankModelPreservesDetectedJinaIdentityWhenOverrideIsApplied'`
  - `2 tests in 1 suite passed`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest tests/integration/test_non_text_endpoints.py -k 'infers_mxbai_family_from_directory_name or infers_causal_lm_from_directory_name' -q`
  - `2 passed, 9 deselected in 22.63s`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_embedding_runtime.py -q`
  - `11 passed in 0.06s`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_rerank_runtime.py -q`
  - `14 passed in 0.06s`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_maintenance_service.py -q`
  - `9 passed in 0.07s`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest tests/integration/test_non_text_endpoints.py -k 'embeddings_endpoint or rerank_endpoint' -q`
  - `8 passed, 3 deselected in 121.12s`
- `swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'phaseFiveSeedModelsExposeTypedCapabilitiesAndRoutes|devEmbeddingModelInfersMXBaiIdentityFromDirectoryName|devEmbeddingModelCoversDirectoryInferenceBranches|devEmbeddingModelDerivesBackendAndFamilyFromOverrides|devRerankModelReadsCausalLMEnvironmentOverrides|devRerankModelPreservesDetectedJinaIdentityWhenOverrideIsApplied|devRerankModelCoversDirectoryInferenceBranches'`
  - `7 tests in 1 suite passed`
- `PYTHONPATH=.:services/mlx-worker-python COVERAGE_FILE=/tmp/m5_5_python.coverage uv run --project services/mlx-worker-python coverage run --source=services/mlx-worker-python/worker,tests/integration -m pytest services/mlx-worker-python/tests/test_embedding_runtime.py services/mlx-worker-python/tests/test_rerank_runtime.py services/mlx-worker-python/tests/test_maintenance_service.py tests/integration/test_non_text_endpoints.py -q`
  - `45 passed in 141.12s`
- `git diff --check`
  - passed

## Metrics

- Python changed-line coverage: `95.45% (105/110)`
- Swift changed-line coverage: `99.57% (229/230)`
- Touched-scope coverage remains above the repository `95%` gate
- Remaining uncovered Swift line:
  - `ModelCatalog.swift:632`

## Acceptance

- architecture and family can be inferred from model metadata and directory structure
- operators can inspect or override the detected identity
- shared embedding and rerank endpoints continue to work when identity comes only from directory naming
