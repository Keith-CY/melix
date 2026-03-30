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
- update `services/control-plane-swift/Tests/ControlPlaneTests/MultimodalContractTests.swift`
- update `services/control-plane-swift/Tests/ControlPlaneTests/TextEndpointContractTests.swift`
- update `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`
- update `services/mlx-worker-python/tests/test_vision_runtime.py`
- update `tests/integration/test_phase6_operator_workflows.py`

## Implementation Notes

- ingress should normalize to one internal image-reference model before runtime dispatch
- remote fetch behavior should remain explicit and measurable
- validation should distinguish unsupported sources from missing sources

## Verification

- `swift test --package-path services/control-plane-swift --filter 'MultimodalContractTests|TextEndpointContractTests|OpenAIHandlerTests'`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_vision_runtime.py tests/integration/test_phase6_operator_workflows.py`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python coverage run --source=worker.runtime.multimodal_preprocessing -m pytest services/mlx-worker-python/tests/test_vision_runtime.py tests/integration/test_phase6_operator_workflows.py`
- `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/Requests/MultimodalRequestNormalizer.swift services/control-plane-swift/Tests/ControlPlaneTests/MultimodalContractTests.swift services/control-plane-swift/Tests/ControlPlaneTests/TextEndpointContractTests.swift services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`

## Acceptance

- local, remote, and inline image inputs are all accepted through the supported multimodal path
- normalization and failure cases are contract-tested

## Coverage

- `services/control-plane-swift/Tests/ControlPlaneTests/MultimodalContractTests.swift`
- `services/control-plane-swift/Tests/ControlPlaneTests/TextEndpointContractTests.swift`
- `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`
- `services/mlx-worker-python/tests/test_vision_runtime.py`
- `tests/integration/test_phase6_operator_workflows.py`

## Metrics

- `vision.preprocess_input_bytes`
- `vision.preprocess_peak_memory_bytes`
- `vision.vlm_first_token_ms`
- `vision.cache_hit_rate`
