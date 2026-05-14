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

## 2026-05-12 OpenAI Chat Tools Compatibility Follow-up

Hermes and OpenAI-compatible SDK clients depend on standard Chat Completions
tool-call semantics. The `/v1/chat/completions` request path must decode
OpenAI `tools` and `tool_choice`, translate function tools into worker
`ToolConfig`, and select an explicit observable parser when a request provides
tools but neither the request nor model metadata selects a parser.

Chat Completions streaming tool-call deltas must be emitted as
`chat.completion.chunk` frames on the standard message SSE channel with
`choices[].delta.tool_calls`. Melix-native metadata may remain in the payload,
but the primary frame shape must be consumable by OpenAI SDK stream parsers.

The worker parser should also treat the `<|tool_call>...<tool_call|>` marker as
a recoverable XML-family fallback when tool parsing is enabled, so raw tool
markup is not exposed as assistant text.

The pipe-call fallback accepts action-qualified names that extend a declared
tool name with `.`, `:`, or `/`, normalizing those calls back to the declared
OpenAI tool name before streaming deltas. Empty argument parentheses may contain
whitespace and are canonicalized to `{}` for downstream JSON consumers.

### Probes And Metrics

- `http.openai_chat_tools_request_count`
- `http.openai_chat_tools_configured_count`
- existing `http.tool_parser_request_count` and parser-mode counters
- worker `tool_call_markup_leak_count` and `malformed_tool_fragment_count`
