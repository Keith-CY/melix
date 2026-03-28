# P4-M3 Completions and Messages Endpoints

## Goal

Make `POST /v1/completions` and `POST /v1/messages` live control-plane endpoints that reuse the shared internal text request model while exposing endpoint-specific SSE envelopes.

## Scope

- Add live `/v1/completions` and `/v1/messages` HTTP handlers.
- Reuse the normalized text request flow introduced in `P4-M1`.
- Add completions-style and messages-style SSE framing for text deltas, usage, terminal completion, and heartbeat or fallback events.
- Add handler-level and integration-level verification for both live endpoints.

## Non-Goals

- Add reasoning or tool-call delta envelopes.
- Add non-streaming payload support for completions or messages.
- Change worker runtime, scheduler, or session semantics beyond endpoint threading.
- Add desktop workflows or endpoint-specific preset logic.

## Implementation Notes

- Keep request normalization in `ChatRequestTranslator`.
- Keep worker execution endpoint-agnostic and shape public stream envelopes in `SSEStreamWriter`.
- Return explicit `stream_required` errors for non-stream completions or messages requests until buffered responses exist.
- Preserve session, branch, and cache hints through the shared normalized request path.

## Performance Probes

- `http.completions_translation_ms`
- `http.messages_translation_ms`
- `http.stream_first_event_ms`
- `http.stream_event_count`
- `http.endpoint_error_rate`

## Verification

- `swift test --package-path services/control-plane-swift --filter TextEndpointContractTests`
- `swift test --package-path services/control-plane-swift --filter '(SSEStreamWriterTests|OpenAIHandlerTests)'`
- `make py-test`
- `make integration-test`
- `git diff --check`

## Acceptance

- `/v1/completions` and `/v1/messages` are live and route through the shared internal text request model.
- Completions and messages SSE frames expose stable endpoint-specific discriminators and terminal events.
- Live integration tests prove both endpoints work through the local control plane stack.
