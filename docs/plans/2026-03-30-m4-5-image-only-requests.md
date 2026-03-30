# M4.5 Image-Only Requests

## Goal

Make image-only vision requests an explicit, contract-tested supported path for the existing OCR and VLM runtimes.

## Scope

- define image-only request validity
- preserve compatibility with prompt-plus-image requests
- keep request normalization and cache identity explicit

## Files

- update `services/control-plane-swift/Tests/ControlPlaneTests/MultimodalContractTests.swift`
- update `services/control-plane-swift/Tests/ControlPlaneTests/TextEndpointContractTests.swift`
- update `services/mlx-worker-python/tests/test_vision_runtime.py`
- update `tests/integration/test_phase6_operator_workflows.py`

## Implementation Notes

- the core normalization and runtime paths already accepted image-only payloads; this slice locks that behavior in with explicit contract and integration coverage
- image-only requests stay distinct from missing-image validation because the payload still carries a valid image part
- VLM image-only requests continue to use the runtime default prompt text while OCR image-only requests return extracted text directly

## Verification

- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python coverage run --include='services/mlx-worker-python/tests/test_vision_runtime.py,tests/integration/test_phase6_operator_workflows.py' -m pytest services/mlx-worker-python/tests/test_vision_runtime.py tests/integration/test_phase6_operator_workflows.py`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python coverage report services/mlx-worker-python/tests/test_vision_runtime.py tests/integration/test_phase6_operator_workflows.py`
- `swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'MultimodalContractTests|TextEndpointContractTests'`
- `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Tests/ControlPlaneTests/MultimodalContractTests.swift services/control-plane-swift/Tests/ControlPlaneTests/TextEndpointContractTests.swift`
- `git diff --check`

## Acceptance

- supported models can execute image-only requests
- image-only validation and failure behavior are contract-tested

## Metrics

- Python touched-scope coverage: `99%` total
- `services/mlx-worker-python/tests/test_vision_runtime.py`: `99%`
- `tests/integration/test_phase6_operator_workflows.py`: `100%`
- Swift changed-line coverage: `100.00% (72/72)`
- Runtime or performance metrics: `N/A` for this slice because the work formalizes existing image-only behavior with test evidence rather than changing runtime performance characteristics
