# M3.11 Streaming Completion And Usage

## Goal

Complete streaming behavior so usage, keepalive, disconnect, and token-by-token tool-call semantics are stable across the supported text endpoints.

## Scope

- add stream usage controls
- preserve keepalive behavior for long-running requests
- detect disconnects and terminate execution safely

## Files

- update `services/control-plane-swift/Sources/HTTPGateway/SSE/SSEStreamWriter.swift`
- update `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`
- update `services/control-plane-swift/Sources/Requests/RequestCoordinator.swift`
- update `tests/integration/`

## Implementation Notes

- stream usage and disconnect behavior should be consistent across endpoints
- disconnect handling should terminate work without corrupting session or cache state
- keepalive cadence should remain measurable and testable

## Verification

- `make swift-test`
- `make integration-test`

## Acceptance

- stream responses can emit usage and keepalive signals where requested
- disconnect behavior is explicit, safe, and integration-tested

## Coverage

- `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`
- `services/control-plane-swift/Tests/HTTPGatewayTests/RequestCoordinatorTests.swift`
- `services/control-plane-swift/Tests/HTTPGatewayTests/SSEStreamWriterTests.swift`
- `tests/integration/test_stream_usage_opt_in.py`
