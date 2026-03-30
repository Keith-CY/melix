# M4.4 Multi-Image Request Semantics

## Goal

Support ordered multi-image VLM prompts end to end and fail explicitly on OCR paths that still only support a single image.

## Scope

- preserve image ordering
- expose multi-image structure through translation and runtime execution
- keep request semantics consistent across vision-capable models

## Files

- update `services/control-plane-swift/Tests/ControlPlaneTests/MultimodalContractTests.swift`
- update `services/mlx-worker-python/worker/runtime/`
- update `services/mlx-worker-python/tests/test_vision_runtime.py`
- update `tests/integration/test_phase6_operator_workflows.py`

## Implementation Notes

- control-plane normalization already preserved part ordering; this slice proves it with explicit contract coverage
- deterministic VLM responses now retain image order by emitting per-image lines for multi-image prompts
- deterministic OCR now rejects multi-image payloads with an explicit preprocessing error instead of silently consuming only the first image

## Verification

- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python coverage run --source=worker.runtime.deterministic_vlm_runtime,worker.runtime.deterministic_ocr_runtime -m pytest services/mlx-worker-python/tests/test_vision_runtime.py tests/integration/test_phase6_operator_workflows.py`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python coverage report services/mlx-worker-python/worker/runtime/deterministic_vlm_runtime.py services/mlx-worker-python/worker/runtime/deterministic_ocr_runtime.py`
- `swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'MultimodalContractTests'`
- `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Tests/ControlPlaneTests/MultimodalContractTests.swift`
- `git diff --check`

## Acceptance

- multi-image requests preserve image ordering and reach the runtime intact
- unsupported multi-image behavior fails explicitly rather than dropping inputs

## Metrics

- Python touched-scope coverage: `99%` total
- `services/mlx-worker-python/worker/runtime/deterministic_ocr_runtime.py`: `100%`
- `services/mlx-worker-python/worker/runtime/deterministic_vlm_runtime.py`: `98%`
- Swift changed-line coverage: `100.00% (42/42)`
- Runtime or performance metrics: `N/A` for this slice because the work changes multimodal semantics and validation behavior rather than adding a new benchmark surface
