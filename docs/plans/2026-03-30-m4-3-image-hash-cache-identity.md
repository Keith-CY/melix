# M4.3 Image Hash Cache Identity

## Goal

Add image hashing to multimodal cache identity so compatible image inputs can participate in cache reuse and deduplication safely.

## Scope

- hash normalized image content
- add image-hash participation to cache identity and restore metadata
- keep cache behavior correct when image ordering or content changes

## Files

- update `services/mlx-worker-python/worker/runtime/multimodal_preprocessing.py`
- update `services/control-plane-swift/Sources/Requests/`
- update `services/control-plane-swift/Sources/Snapshots/`
- update `services/mlx-text-worker-swift/Sources/Core/`

## Implementation Notes

- hash identity should operate on normalized bytes rather than raw request strings
- image ordering should remain part of the request identity where semantically meaningful
- metrics should distinguish vision-hash reuse from text-only reuse

## Verification

- `make py-test`
- `make swift-test`
- `make integration-test`

## Acceptance

- image hashes are part of multimodal cache identity
- cache reuse changes predictably when image content changes
