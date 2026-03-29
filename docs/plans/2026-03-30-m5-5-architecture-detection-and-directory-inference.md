# M5.5 Architecture Detection And Directory Inference

## Goal

Add architecture detection and directory-level inference so model-family routing stops depending on manual hardcoded registration.

## Scope

- infer architecture and family from model metadata and directory structure
- preserve explicit overrides where needed
- keep detection results visible to operators and diagnostics

## Files

- update `services/mlx-worker-python/worker/model_registry/catalog.py`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `services/mlx-worker-python/worker/engine/maintenance_core.py`
- update `tests/integration/`

## Implementation Notes

- detection should prefer explicit manifests over brittle path heuristics when available
- overrides must remain possible for ambiguous or incomplete artifacts
- diagnostics should expose both detected and overridden identity

## Verification

- `make py-test`
- `make integration-test`

## Acceptance

- architecture and family can be inferred from model metadata and directory structure
- operators can inspect or override the detected identity
