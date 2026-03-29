# M8.3 HuggingFace Search, Pagination, And Cards

## Goal

Add productized HuggingFace discovery with search, pagination, and model-card inspection for MLX-relevant artifacts.

## Scope

- add search and pagination
- add model-card inspection
- keep discovery flows operator-visible and compatible with offline-first product expectations

## Files

- update `services/mlx-worker-python/worker/model_ops/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `docs/runbooks/`

## Implementation Notes

- discovery metadata should remain distinct from local registry metadata
- model-card payloads should be normalized before UI consumption
- preserve room for MLX-only filtering and mirror support in later slices

## Verification

- `make py-test`
- `make swift-test`

## Acceptance

- operators can search, page through, and inspect Hub model metadata
- discovery results are normalized and test-covered
