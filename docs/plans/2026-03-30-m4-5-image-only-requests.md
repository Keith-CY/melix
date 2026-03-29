# M4.5 Image-Only Requests

## Goal

Allow supported vision-family models to handle image-only requests without requiring synthetic text prompts.

## Scope

- define image-only request validity
- preserve compatibility with prompt-plus-image requests
- keep request normalization and cache identity explicit

## Files

- update `services/control-plane-swift/Sources/Requests/MultimodalRequestNormalizer.swift`
- update `services/mlx-worker-python/worker/runtime/`
- update `services/control-plane-swift/Tests/ControlPlaneTests/`
- update `tests/integration/test_phase6_operator_workflows.py`

## Implementation Notes

- image-only requests should remain distinct from missing-text validation errors
- model-family compatibility must be explicit and visible to operators
- output behavior should remain protocol-compatible with existing chat surfaces

## Verification

- `make swift-test`
- `make py-test`
- `make integration-test`

## Acceptance

- supported models can execute image-only requests
- image-only validation and failure behavior are contract-tested
