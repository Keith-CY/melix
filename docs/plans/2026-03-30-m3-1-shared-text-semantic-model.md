# M3.1 Shared Text Semantic Model

## Goal

Complete a single internal semantic model for chat, completions, responses, and messages so protocol translation stops leaking endpoint-specific behavior into execution logic.

## Scope

- unify internal request semantics across text endpoints
- keep endpoint-specific wire framing at the HTTP translation boundary
- preserve existing session, workflow, and cache shaping hooks

## Files

- update `services/control-plane-swift/Sources/Requests/ChatRequestTranslator.swift`
- update `services/control-plane-swift/Sources/Requests/TextRequestShaper.swift`
- update `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`
- update `services/control-plane-swift/Tests/ControlPlaneTests/`

## Implementation Notes

- shared semantics should represent messages, system content, workflow hints, and restore intent consistently
- HTTP framing differences should remain at the final encoding layer
- avoid endpoint-specific execution branches after translation completes

## Verification

- `make swift-test`
- `make integration-test`

## Acceptance

- all text endpoints normalize into one internal request model
- endpoint-specific differences are limited to translation and response framing
