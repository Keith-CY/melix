# M3.2 Anthropic-Compatible Fields And Thinking Blocks

## Goal

Add the missing request and response fields needed for the Anthropic-compatible surface, including explicit thinking-block support.

## Scope

- complete request-field compatibility where currently absent
- represent thinking blocks explicitly rather than only as generic reasoning deltas
- preserve the shared internal text semantic model

## Files

- update `services/control-plane-swift/Sources/Requests/ChatRequestTranslator.swift`
- update `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`
- update `services/control-plane-swift/Sources/HTTPGateway/SSE/SSEStreamWriter.swift`
- update `tests/integration/test_messages_stream.py`

## Implementation Notes

- compatibility should be expressed through translation, not endpoint-specific execution forks
- thinking blocks should remain compatible with later budget and reasoning-separation work
- use structured fields rather than implicit string conventions

## Verification

- `make swift-test`
- `make integration-test`

## Acceptance

- the messages surface exposes the missing compatibility fields
- thinking-block behavior is represented explicitly and is test-covered
