# M4.1 Native VLM Runtime Lifecycle

## Goal

Introduce a native VLM runtime lifecycle with explicit prefill, decode, and runtime-state handling rather than a contract-only path.

## Scope

- define VLM runtime lifecycle entrypoints
- add lifecycle metrics and state transitions
- preserve multimodal request normalization while runtime depth lands

## Files

- update `services/mlx-worker-python/worker/runtime/deterministic_vlm_runtime.py`
- update `services/mlx-worker-python/worker/engine/engine_core.py`
- update `services/mlx-worker-python/worker/engine/request_state.py`
- update `services/mlx-worker-python/worker/registry.py`
- update `services/mlx-worker-python/worker/grpc_server.py`
- update `services/mlx-worker-python/worker/control_plane_bridge.py`
- update `services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift`
- update `services/control-plane-swift/Sources/WorkerClient/WorkerRoute.swift`
- update `services/control-plane-swift/Sources/Requests/RequestCoordinator.swift`
- update `services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`
- update `services/control-plane-swift/Tests/HTTPGatewayTests/RequestCoordinatorTests.swift`
- update `services/mlx-worker-python/tests/test_control_plane_bridge.py`
- update `services/mlx-worker-python/tests/test_generate_stream.py`
- update `services/mlx-worker-python/tests/test_vision_runtime.py`
- add `tests/integration/test_vlm_phase_aware_lifecycle.py`

## Implementation Notes

- the VLM lifecycle should align with the shared scheduling and cache model
- keep OCR-specific behavior out of the generic VLM runtime contract
- avoid a second control-plane path just for vision execution

## Verification

- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_generate_stream.py services/mlx-worker-python/tests/test_control_plane_bridge.py services/mlx-worker-python/tests/test_runtime_edges.py services/mlx-worker-python/tests/test_vision_runtime.py`
- `swift test --package-path services/control-plane-swift --filter 'PythonBridgeWorkerClientTests|RequestCoordinatorTests'`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python pytest tests/integration/test_phase6_operator_workflows.py tests/integration/test_vlm_phase_aware_lifecycle.py`
- `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python coverage run --source=services/mlx-worker-python/worker -m pytest services/mlx-worker-python/tests tests/integration/test_vlm_phase_aware_lifecycle.py`
- `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift services/control-plane-swift/Sources/WorkerClient/WorkerRoute.swift services/control-plane-swift/Sources/Requests/RequestCoordinator.swift services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift services/control-plane-swift/Tests/HTTPGatewayTests/RequestCoordinatorTests.swift`

## Acceptance

- VLM execution has an explicit runtime lifecycle with observable state transitions
- prefill and decode are available through the worker gRPC surface and the python bridge
- background-lane VLM requests can use the shared phase-aware coordinator path
- live VLM requests no longer depend only on a monolithic generate-only placeholder path

## Coverage

- `services/mlx-worker-python/tests/test_control_plane_bridge.py`
- `services/mlx-worker-python/tests/test_generate_stream.py`
- `services/mlx-worker-python/tests/test_runtime_edges.py`
- `services/mlx-worker-python/tests/test_vision_runtime.py`
- `services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`
- `services/control-plane-swift/Tests/HTTPGatewayTests/RequestCoordinatorTests.swift`
- `tests/integration/test_phase6_operator_workflows.py`
- `tests/integration/test_vlm_phase_aware_lifecycle.py`

## Metrics

- `active_prefills`
- `active_decodes`
- `last_probe_kind`
- `last_preprocess_latency_ms`
- `last_first_token_latency_ms`
