# M3.4 Harmony Protocol Compatibility

## Goal

Add compatibility for harmony-style request and response semantics without introducing a second internal text runtime model.

## Scope

- add translation at the HTTP boundary
- map harmony semantics into the shared text semantic model
- keep streaming and completed-output behavior aligned with the existing execution path

## Files

- update `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`
- update `services/control-plane-swift/Sources/Requests/ChatRequestTranslator.swift`
- update `services/control-plane-swift/Tests/HTTPGatewayTests/`

## Implementation Notes

- compatibility should stay in the translation layer
- request metadata must preserve enough fidelity for later tool-calling and reasoning integration
- avoid wire-shape drift between live and non-stream responses

## Verification

- `make swift-test`
- `make integration-test`

## Acceptance

- harmony-compatible inputs can be translated into Melix execution requests
- streaming and completed outputs are contract-tested
