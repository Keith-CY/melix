# P4-M2 Responses Endpoint Streaming

## Goal

Make `POST /v1/responses` a live control-plane endpoint that reuses the shared internal text request model and emits a stable responses-style SSE stream.

## Scope

- Add the live `/v1/responses` HTTP handler.
- Reuse the normalized text request path introduced in `P4-M1`.
- Add responses-specific SSE framing for text deltas, usage, terminal completion, and heartbeat events.
- Add handler-level and integration-level verification for the live responses stream.

## Non-Goals

- Add `/v1/completions` or `/v1/messages` live handlers.
- Add reasoning or tool-call delta payloads beyond generic stream-shape support.
- Change worker runtime semantics or scheduler behavior.
- Add non-streaming responses payload support.

## Implementation Notes

- Keep request normalization in `ChatRequestTranslator`.
- Keep worker execution endpoint-agnostic and shape the public stream envelope in `SSEStreamWriter`.
- Return explicit `stream_required` errors for non-stream responses requests until a buffered responses path exists.
- Treat `/v1/responses` as the first live Phase 4 endpoint after `chat/completions`, so the integration path must be operator-usable.

## Performance Probes

- `http.responses_translation_ms`
- `http.stream_first_event_ms`
- `http.stream_event_count`
- `http.endpoint_error_rate`

## Verification

- `swift test --package-path services/control-plane-swift --filter SSEStreamWriterTests`
- `swift test --package-path services/control-plane-swift --filter OpenAIHandlerTests`
- `make py-test`
- `make integration-test`
- `git diff --check`

## Acceptance

- `/v1/responses` accepts streamed text requests and routes through the shared internal request model.
- Responses SSE frames expose stable `response.output_text.delta`, `response.usage`, and `response.completed` events.
- A live integration test proves the endpoint works through the local control plane stack.
