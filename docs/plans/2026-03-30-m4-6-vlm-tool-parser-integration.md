# M4.6 VLM Tool Parser Integration

## Goal

Connect VLM execution to the shared tool parser layer so vision requests can participate in tool calling with the same parser infrastructure as text models.

## Scope

- route VLM output through parser selection
- preserve multimodal prompt structure while parsing tool calls
- keep streaming and completed parsing behavior aligned

## Files

- update `services/mlx-worker-python/worker/runtime/`
- update `services/control-plane-swift/Sources/Requests/`
- update `services/control-plane-swift/Sources/HTTPGateway/SSE/`
- update `tests/integration/`

## Implementation Notes

- parser selection should remain model-aware and request-aware
- tool-call parsing must preserve multimodal context boundaries rather than flatten them away
- avoid VLM-only parser branches that diverge from the shared parser registry

## Verification

- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_generate_stream.py services/mlx-worker-python/tests/test_vision_runtime.py -q`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest tests/integration/test_phase6_operator_workflows.py -k 'tool_calls_with_shared_parser_selection' -q`
- `swift test --package-path services/control-plane-swift --filter 'ToolParserRegistryTests|RequestCoordinatorTests'`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python coverage run --include='services/mlx-worker-python/worker/engine/engine_core.py,services/mlx-worker-python/worker/runtime/deterministic_ocr_runtime.py,services/mlx-worker-python/worker/runtime/deterministic_vlm_runtime.py,services/mlx-worker-python/worker/runtime/mlx_text_runtime.py,services/mlx-worker-python/tests/test_generate_stream.py,services/mlx-worker-python/tests/test_vision_runtime.py,tests/integration/test_phase6_operator_workflows.py' -m pytest services/mlx-worker-python/tests/test_generate_stream.py services/mlx-worker-python/tests/test_vision_runtime.py tests/integration/test_phase6_operator_workflows.py`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python coverage json -o /tmp/m4_6_python_coverage.json`
- `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/m4_6_python_coverage.json services/mlx-worker-python/worker/engine/engine_core.py services/mlx-worker-python/worker/runtime/deterministic_ocr_runtime.py services/mlx-worker-python/worker/runtime/deterministic_vlm_runtime.py services/mlx-worker-python/worker/runtime/mlx_text_runtime.py services/mlx-worker-python/tests/test_vision_runtime.py tests/integration/test_phase6_operator_workflows.py`
- `swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'ToolParserRegistryTests|RequestCoordinatorTests'`
- `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Tests/ControlPlaneTests/ToolParserRegistryTests.swift services/control-plane-swift/Tests/HTTPGatewayTests/RequestCoordinatorTests.swift`

## Acceptance

- VLM requests can emit parsed tool calls through the shared parser stack
- stream and completed behaviors are integration-tested

## Metrics Report

- Python changed-line coverage: `97.35% (110/113)` across the touched worker and integration files
- Swift changed-line coverage: `99.34% (151/152)` across the touched control-plane test files
- Live multimodal parser integration: `1/1` targeted phase 6 operator workflow test passed
