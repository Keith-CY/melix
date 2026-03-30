# M16.1 Video Ingress And Media-Normalization Contracts

## Goal

Define one explicit contract for accepted video inputs, media metadata, and preprocessing bounds so Melix can reason about video requests without leaking transport-specific assumptions into runtime code.

## Scope

- add normalized video-input fields and validation rules
- define accepted local, remote, and inline media forms
- expose duration, frame-budget, and preprocessing-bound metadata

## Files

- update `packages/protocol/schema/`
- update `services/control-plane-swift/Sources/Requests/`
- update `services/mlx-worker-python/worker/runtime/`

## Implementation Notes

- Video normalization should share concepts with image and audio ingress where possible, but duration and frame-budget metadata must remain explicit.
- Unsupported containers, missing metadata, and oversized preprocessing requests should fail with structured errors.

## Verification

- `make proto`
- `make swift-test`
- `make py-test`

## Acceptance

- Video ingress is normalized and test-covered across supported source forms.
- Duration, frame-budget, and validation failures are inspectable through the shared request model.
