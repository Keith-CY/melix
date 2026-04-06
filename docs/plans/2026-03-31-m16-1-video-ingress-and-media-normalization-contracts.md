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

## Completion Notes

- Completed on `2026-04-06`.
- Implemented shared protocol fields for `video_uri`, `video_bytes`, `MEDIA_TYPE_VIDEO`,
  `frame_budget`, `start_ms`, and `end_ms`.
- Added Swift-side `input_video` normalization and Python-side `video_preprocessing.py` contract
  validation without introducing frame extraction or scheduler-routing behavior.

## Verification Results

- `make proto`
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'MultimodalContractTests|videoBearingVLMRequestsStayDispatchableDuringIngressOnlyRollout'`
- `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/Requests/MultimodalRequestNormalizer.swift services/control-plane-swift/Sources/Requests/RequestCoordinator.swift services/control-plane-swift/Tests/ControlPlaneTests/MultimodalContractTests.swift services/control-plane-swift/Tests/HTTPGatewayTests/RequestCoordinatorTests.swift`
- `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_multimodal_contracts.py services/mlx-worker-python/tests/test_video_preprocessing.py -q`
- `cd services/mlx-worker-python && PYTHONPATH='.:..:../..' uv run coverage run --source=worker/runtime,tests -m pytest tests/test_multimodal_contracts.py tests/test_video_preprocessing.py -q && PYTHONPATH='.:..:../..' uv run coverage report -m worker/runtime/video_preprocessing.py tests/test_multimodal_contracts.py tests/test_video_preprocessing.py`
