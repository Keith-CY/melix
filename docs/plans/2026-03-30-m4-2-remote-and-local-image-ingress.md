# M4.2 Remote And Local Image Ingress

## Goal

Support remote URLs, local paths, and inline payloads through one normalized image-ingress path for multimodal requests.

## Scope

- add `http` and `https` image ingress
- preserve local-path and inline payload support
- keep request normalization shared across text and vision-family APIs

## Files

- update `services/control-plane-swift/Sources/Requests/MultimodalRequestNormalizer.swift`
- update `services/mlx-worker-python/worker/runtime/multimodal_preprocessing.py`
- update `services/control-plane-swift/Tests/ControlPlaneTests/`
- update `tests/integration/test_phase6_operator_workflows.py`

## Implementation Notes

- ingress should normalize to one internal image-reference model before runtime dispatch
- remote fetch behavior should remain explicit and measurable
- validation should distinguish unsupported sources from missing sources

## Verification

- `make swift-test`
- `make py-test`
- `make integration-test`

## Acceptance

- local, remote, and inline image inputs are all accepted through the supported multimodal path
- normalization and failure cases are contract-tested
