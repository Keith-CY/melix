# M5.2 BGE And MXBAI Family Support

## Goal

Add family-specific support for `bge` and `mxbai` style embedding models on top of the native embedding backend layer.

## Scope

- add family adapters and configuration rules
- preserve the generic embedding endpoint contract
- expose family capabilities through model registry metadata

## Files

- update `services/mlx-worker-python/worker/model_registry/catalog.py`
- update `services/mlx-worker-python/worker/runtime/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `tests/integration/`

## Implementation Notes

- family adapters should own pooling and output-shape differences where they exist
- registry metadata should make family identity explicit to operators
- avoid embedding-family branching in the control plane

## Verification

- `make py-test`
- `make integration-test`

## Acceptance

- `bge` and `mxbai` style models can be registered and served through the embedding path
- family-specific behavior is test-covered
