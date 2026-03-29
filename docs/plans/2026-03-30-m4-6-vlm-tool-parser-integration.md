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

- `make py-test`
- `make swift-test`
- `make integration-test`

## Acceptance

- VLM requests can emit parsed tool calls through the shared parser stack
- stream and completed behaviors are integration-tested
