# P4-M4 Reasoning and Tool Deltas

## Goal

Make reasoning and tool-call deltas explicit, ordered, and endpoint-aware across the live text endpoint family without changing the underlying text runtime contract.

## Scope

- `services/control-plane-swift/Sources/HTTPGateway/SSE/*`
- `services/control-plane-swift/Sources/Requests/*`
- `services/control-plane-swift/Tests/HTTPGatewayTests/*`
- `docs/README.md`

## Non-Goals

- Add new worker-side reasoning or tool parsing behavior.
- Change the public request shapes for chat, completions, responses, or messages.
- Introduce endpoint-specific runtime routing.
- Add desktop foundation work.

## Design

- Keep worker output generic through `ExecuteEvent.reasoning_delta` and `ExecuteEvent.tool_call_delta`.
- Normalize stream behavior in the control plane only.
- Preserve upstream ordering exactly; the control plane should shape envelopes, not reorder semantic events.
- Emit endpoint-specific SSE event names and payload shapes:
  - chat completions: chat-compatible delta envelopes plus Melix-native reasoning and tool delta event names
  - completions: completion-specific reasoning and tool delta envelopes
  - responses: `response.reasoning.delta` and `response.tool_call.delta`
  - messages: `message.reasoning.delta` and `message.tool_call.delta`
- Record basic control-plane metrics for reasoning and tool delta counts and first semantic stream event latency.

## Performance Probes

- `http.stream_first_event_ms`
- `http.reasoning_delta_count`
- `http.tool_delta_count`

## Work Steps

1. Add failing SSE writer tests for reasoning and tool-call delta framing across all text endpoint shapes.
2. Add one control-plane handler test proving a live endpoint forwards worker reasoning and tool-call deltas into the expected SSE stream.
3. Implement endpoint-specific reasoning and tool delta encoding plus first-semantic-event and delta-count metrics.
4. Run focused Swift tests, full Python tests, integration tests, focused coverage, and diff check.

## Verification

```bash
swift test --package-path services/control-plane-swift --filter '(SSEStreamWriterTests|OpenAIHandlerTests)'
make py-test
make integration-test
/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swift test --package-path services/control-plane-swift --scratch-path /tmp/melix-control-plane-p4m4-coverage --enable-code-coverage --filter '(SSEStreamWriterTests|OpenAIHandlerTests)'
git diff --check
```

## Acceptance

- Every text endpoint shape emits explicit reasoning and tool delta frames when upstream worker events are present.
- Event ordering remains invariant across chat, completions, responses, and messages.
- Touched control-plane HTTP gateway scope remains at or above `95%` coverage.
- Metrics report includes reasoning delta count, tool delta count, and first semantic event latency or an explicit `N/A` reason.
