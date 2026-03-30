# M14.1 Image Variation And Iterate Request Semantics

## Goal

Define the request and artifact semantics for image variations and iterate flows on top of the existing image-job model.

## Scope

- add variation and iterate request shapes
- preserve artifact lineage through source and derived outputs
- keep iteration flows compatible with existing image jobs

## Files

- update `packages/protocol/schema/controlplane/v1/`
- update `packages/protocol/schema/worker/v1/`
- update `services/control-plane-swift/Sources/`
- update `services/mlx-worker-python/worker/`

## Implementation Notes

- Iterate should reference prior artifact identity rather than bypassing job history.
- Variation semantics should make strength and prompt-delta behavior explicit.
- Artifact lineage should remain visible to both runtime and desktop consumers.

## Verification

- `make proto`
- `make swift-test`
- `make py-test`

## Acceptance

- Variation and iterate flows are typed, explicit, and compatible with the image-job model.
