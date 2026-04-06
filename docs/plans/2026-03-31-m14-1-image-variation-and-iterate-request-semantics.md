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

## Executable Slices

### Slice 1: Typed Variation And Iterate Contract

- add typed image edit mode fields for `edit`, `variation`, and `iterate`
- allow edit requests to reference a prior image artifact by stable `source_artifact_id`
- preserve `source_artifact_id`, resolved parent job identity, and `prompt_delta` lineage through
  worker artifact metadata and control-plane image job summaries
- keep existing raw `image` and `image_uri` edit flows backward compatible

Status: completed on 2026-04-06.

## Verification

- `make proto`
- `make swift-test`
- `make py-test`

## Acceptance

- Variation and iterate flows are typed, explicit, and compatible with the image-job model.
