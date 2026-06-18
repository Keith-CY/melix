# Issue 42 U2.2.3 Streaming Budget Parity Fixtures

## Source

- GitHub issue: <https://github.com/Keith-CY/melix/issues/1452>
- Parent plan: <https://github.com/Keith-CY/melix/issues/1430>
- Governing roadmap: `docs/plans/2026-04-26-issue-42-multimodal-fast-paths.md`
- Prior slices:
  - `docs/plans/2026-05-24-issue-42-u2-2-1-attention-cost-auto-chunk-policy.md`
  - `docs/plans/2026-05-25-issue-42-u2-2-2-chunked-auxiliary-tensor-slicing.md`

## Goal

Add regression fixtures that prove over-budget VLM attention admission behaves
the same for streaming and non-streaming OpenAI chat requests, including the
public HTTP boundary before any SSE bytes are emitted.

## Architecture

The Python worker owns VLM execution truth and already emits a typed
`multimodal_prefill_attention_budget_exceeded` error event before decode when a
media-expanded attention estimate exceeds the active budget. The Swift HTTP
gateway owns the OpenAI API contract and must not start a server-sent-events
response when the first worker event is that admission refusal.

This slice keeps the attention-cost calculation in the worker. The gateway adds
a narrow first-event inspection path for streaming chat: if the first worker
event is a typed admission refusal, return the existing OpenAI JSON error
envelope instead of `text/event-stream`; otherwise replay the first event and
continue streaming normally.

## Behavior Contract

- Streaming and non-streaming VLM requests with the same prompt, media, model,
  and token cap surface the same worker error code.
- Streaming over-budget VLM requests return an HTTP JSON error response before
  the first SSE data frame. The response body must not be `.stream`.
- The OpenAI JSON error envelope preserves typed worker details:
  `predicted_attention_bytes`, `attention_budget_bytes`,
  `auto_chunk_reason`, `prefill_chunk_mode`, and
  `selected_prefill_step_size`.
- Normal streaming requests keep the current SSE behavior by replaying any
  first event consumed during admission inspection.

## Implementation Steps

1. Add a failing HTTP gateway test in
   `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`
   that scripts a first worker error event for a media-bearing VLM chat request
   with `stream=true` and asserts JSON 400, no SSE body, and typed attention
   details.
2. Add a paired non-streaming fixture for the same media prompt and worker
   error event, asserting the same error code and detail fields.
3. Add a small helper in
   `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`
   that reads the first worker event before creating an SSE response, maps
   first-event admission errors to `workerErrorResponse`, and otherwise returns
   a stream that replays the first event.
4. Run the new tests first to confirm the red state, then implement the helper
   and verify the focused Swift tests turn green.
5. Run full local gates and build the scoped performance report before opening
   the pull request.

## Performance Probes And Success Metrics

- Measurement point: OpenAI chat streaming response setup in
  `OpenAIHandler.streamResponse`.
- Success metric: PR-scoped performance report has status `ok` with no
  regression. This slice adds one first-event await on streaming text requests;
  the PR report must confirm no selected probe regression for the changed
  scope.
- Observability mode: minimal. No new runtime counters or evidence-mode probes
  are added because the behavior is a public error-boundary fixture.
- Probe overhead: N/A for new probes; this slice does not add a production
  probe. Existing PR-scoped performance infrastructure is used.

## Verification

Required focused checks before PR handoff:

- `swift test --package-path services/control-plane-swift --filter OpenAIHandlerTests`
- `make swift-test`
- `make py-test`
- `make integration-test`
- Scoped PR performance report with status `ok` and zero regressions.

Changed-scope coverage must be reported before commit. If the Swift package
coverage tooling cannot measure the touched scope directly, record the focused
test coverage limitation and include the focused test pass plus full Swift gate.

## Non-Goals

- No protobuf schema change.
- No change to the worker attention-cost estimator.
- No throughput claim for VLM chunking.
- No change to unrelated SSE error frames that occur after a normal streaming
  response has already started.
