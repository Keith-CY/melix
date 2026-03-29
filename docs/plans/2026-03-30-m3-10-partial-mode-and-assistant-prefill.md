# M3.10 Partial Mode And Assistant Prefill

## Goal

Support partial-mode execution and assistant-prefill semantics without creating a separate execution path outside the shared text model.

## Scope

- represent partial-mode semantics in request translation
- preserve assistant name passthrough where required
- keep cache and restore behavior compatible with assistant-prefill flows

## Files

- update `services/control-plane-swift/Sources/Requests/ChatRequestTranslator.swift`
- update `services/control-plane-swift/Sources/Requests/TextRequestShaper.swift`
- update `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`
- update `services/control-plane-swift/Tests/ControlPlaneTests/`

## Implementation Notes

- partial mode should remain a request-shaping concern rather than a forked runtime
- assistant-prefill metadata should compose cleanly with cache identity and session continuity
- name passthrough should be preserved through stream and completed outputs

## Verification

- `make swift-test`
- `make integration-test`

## Acceptance

- partial-mode requests can be represented and executed through the shared text path
- assistant-prefill metadata and name passthrough are integration-tested
