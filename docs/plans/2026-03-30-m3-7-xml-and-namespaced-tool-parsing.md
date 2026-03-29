# M3.7 XML And Namespaced Tool Parsing

## Goal

Extend tool parsing to support XML-style fallback formats and namespaced tool-call formats without special-case endpoint logic.

## Scope

- add XML fallback parsing
- add namespaced tool-call parsing
- preserve existing parser-registry selection rules

## Files

- update `services/control-plane-swift/Sources/Requests/`
- update `services/control-plane-swift/Sources/HTTPGateway/SSE/SSEStreamWriter.swift`
- update `services/control-plane-swift/Tests/HTTPGatewayTests/`

## Implementation Notes

- fallback parsing should be explicit and metrics-visible rather than silent
- namespaced tool-call handling should preserve tool identity and arguments separately
- keep parser behavior deterministic across stream and completed outputs

## Verification

- `make swift-test`
- `make integration-test`

## Acceptance

- XML-style and namespaced tool-call formats can be parsed through the shared parser layer
- fallback parsing behavior is observable and test-covered
