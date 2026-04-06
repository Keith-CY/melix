# M9.6 Connection Lifecycle Slice

**Goal:** Land the first executable `M9.6` slice by turning chat streaming into a policy-driven, resume-aware lifecycle with measurable keepalive and disconnect recovery metrics.

## Scope

- add a typed `ConnectionLifecyclePolicy`
- replace immediate stream-disconnect aborts with bounded disconnect grace and explicit terminal expiry
- add resumable chat execution attachment for control-plane and HTTP chat callers
- capture keepalive-gap, recovery-latency, resume-success-rate, and terminal-failure metrics
- close the slice with focused Swift tests, live integration coverage, a smoke script, and a runbook

## Planned Files

- add `services/control-plane-swift/Sources/HTTPGateway/SSE/ConnectionLifecyclePolicy.swift`
- modify `services/control-plane-swift/Sources/HTTPGateway/SSE/SSEStreamWriter.swift`
- modify `services/control-plane-swift/Sources/Requests/RequestCoordinator.swift`
- modify `services/control-plane-swift/Sources/Requests/ChatRequestTranslator.swift`
- modify `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`
- modify `services/control-plane-swift/Sources/XPCService/ControlPlaneChatExecution.swift`
- modify `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- modify `services/control-plane-swift/Tests/HTTPGatewayTests/SSEStreamWriterTests.swift`
- modify `services/control-plane-swift/Tests/HTTPGatewayTests/RequestCoordinatorTests.swift`
- modify `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`
- modify `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneChatExecutionTests.swift`
- modify `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
- add `tests/integration/test_connection_lifecycle.py`
- add `scripts/m9_connection_smoke.py`
- add `docs/runbooks/connection-lifecycle.md`

## Red-Green Sequence

1. Add failing Swift tests for:
   - keepalive-gap metrics
   - disconnect grace delaying worker abort
   - successful resume cancelling the pending abort
   - expired disconnect grace producing an explicit terminal failure
2. Implement the minimum lifecycle policy, resumable execution hub, and chat resume path to make those tests pass.
3. Add failing integration and smoke coverage for live disconnect-resume and disconnect-timeout flows.
4. Implement the remaining HTTP and runbook surfaces.

## Verification

- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'SSEStreamWriterTests|RequestCoordinatorTests|OpenAIHandlerTests|ControlPlaneChatExecutionTests|ControlPlaneServiceTests'`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest tests/integration/test_recovery_flows.py tests/integration/test_connection_lifecycle.py -q`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/m9_connection_smoke.py --json`
- changed-line coverage for the touched executable scope via `scripts/swift_changed_line_coverage.py` and the repository Python coverage path

## Commit Target

- `feat: harden connection lifecycle recovery`
