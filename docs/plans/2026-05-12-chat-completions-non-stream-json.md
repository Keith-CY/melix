# Chat Completions Non-Stream JSON

Date: 2026-05-12

## Summary

`POST /v1/chat/completions` must support the OpenAI-compatible non-streaming
response shape when callers omit `stream` or send `"stream": false`. The current
gateway always returns Server-Sent Events unless the caller explicitly sends
`stream: false`, which is rejected with `stream_required`. That breaks clients
that use chat completions for short auxiliary calls and expect a JSON object.

## Scope

- Keep `stream: true` chat completions on the existing SSE path.
- Buffer worker execution events for `POST /v1/chat/completions` when
  `stream` is omitted or false, then return one `chat.completion` JSON object.
- Request worker usage accounting for buffered responses so the final JSON can
  include `usage` when the worker reports it.
- Preserve existing `stream_required` behavior for `/v1/completions`,
  `/v1/responses`, and `/v1/messages`.
- Add HTTP gateway unit tests for explicit `stream: false`, omitted `stream`,
  and the existing streaming path.

## Non-Goals

- Add non-stream responses for every text endpoint.
- Change worker RPC streaming semantics.
- Add multi-choice buffering or tool-call reconstruction beyond preserving
  existing stream behavior.
- Change resume semantics; `resume_request_id` remains an SSE resume operation.

## Design

The worker still emits an ordered stream of `ExecuteEvent` messages. The HTTP
gateway adds a chat-completions-only response path that consumes that stream,
aggregates text deltas, records usage deltas, and uses the terminal completion
event as the authoritative finish reason and assistant text when available.

The JSON response shape is:

```json
{
  "id": "<request_id>",
  "object": "chat.completion",
  "created": 1778520000,
  "model": "<model_id>",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "<assistant text>"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 1,
    "completion_tokens": 2,
    "total_tokens": 3
  }
}
```

If no worker usage event is emitted, `usage` is omitted instead of fabricating
zero-token accounting.

If the worker emits an error event while the gateway is buffering a non-stream
chat completion, that error terminates aggregation immediately. The gateway
returns the mapped worker error response and ignores any later stream events.

## Metrics

The HTTP gateway records:

- `http.chat_completions_non_stream_request_count`
- `http.chat_completions_non_stream_latency_ms`
- `http.chat_completions_non_stream_completion_tokens` as a cumulative counter

Success means the explicit and default non-stream tests exercise the new JSON
path, the existing SSE test remains unchanged, and changed-line coverage for the
edited Swift HTTP gateway scope is at least 95 percent.

## Verification

Run:

```bash
HOME="$(pwd)/.swift-home" \
CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" \
swift test --package-path services/control-plane-swift --filter OpenAIHandlerTests

HOME="$(pwd)/.swift-home" \
CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" \
swift test --package-path services/control-plane-swift --enable-code-coverage --filter OpenAIHandlerTests
```

Then report changed-scope coverage from the generated Swift coverage artifacts.
