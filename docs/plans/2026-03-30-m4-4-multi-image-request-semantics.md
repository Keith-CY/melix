# M4.4 Multi-Image Request Semantics

## Goal

Support multi-image prompts as first-class multimodal requests instead of silently collapsing to a single effective image.

## Scope

- preserve image ordering
- expose multi-image structure through translation and runtime execution
- keep request semantics consistent across vision-capable models

## Files

- update `services/control-plane-swift/Sources/Requests/`
- update `services/mlx-worker-python/worker/runtime/`
- update `tests/integration/test_phase6_operator_workflows.py`

## Implementation Notes

- the runtime contract should distinguish zero, one, and many image inputs explicitly
- ordering rules must remain stable and testable
- do not hide unsupported model behavior behind silent truncation

## Verification

- `make swift-test`
- `make py-test`
- `make integration-test`

## Acceptance

- multi-image requests preserve image ordering and reach the runtime intact
- unsupported multi-image behavior fails explicitly rather than dropping inputs
