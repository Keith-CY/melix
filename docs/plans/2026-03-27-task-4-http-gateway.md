# Melix Task 4 Execution Plan: HTTP Chat Gateway, SSE Streaming, and Abort Bridge

## Scope

This plan executes Task 4 from `docs/plans/2026-03-27-phase-0-thin-path.md`.

The slice stays intentionally narrow:

- `POST /v1/chat/completions`
- `GET /v1/models`
- request-to-worker `Generate` translation
- streaming SSE output for content, usage, heartbeat, terminal completion, and errors
- cancellation from the control plane to worker `Abort`

The slice does not add:

- `responses` or `messages` APIs
- embeddings, rerank, image, or audio endpoints
- multi-lane scheduling
- real worker transport beyond the control-plane abstraction

## Architecture Boundaries

- The HTTP gateway is owned by the Swift control plane.
- The request coordinator owns admission, request identity creation, and abort bookkeeping.
- The worker client abstraction owns streaming execution and abort transport.
- The model catalog remains the source of truth for `GET /v1/models`.
- SSE formatting remains a transport concern and must not contain scheduling logic.

## Planned Changes

### Test-First Work

Add failing Swift tests for:

- chat-completions request translation into a worker `GenerateRequest`
- SSE framing order for deltas, usage, heartbeat, completion, and errors
- models endpoint projection from the in-memory model catalog
- abort propagation from the control plane to the worker client

### Production Work

Add the following control-plane components:

- `HTTPGateway/OpenAI/OpenAIHandler.swift`
- `HTTPGateway/SSE/SSEStreamWriter.swift`
- `Requests/ChatRequestTranslator.swift`
- `Requests/RequestCoordinator.swift`
- `Requests/AbortRegistry.swift`

Also extend the worker client abstraction so the control plane can:

- stream execute events for `Generate`
- forward `Abort`

## Performance Probes and Success Metrics

The changed path must be measurable from the first implementation.

Required probes:

- request translation latency in the control plane
- worker dispatch start time and terminal completion time
- time-to-first-delta at the coordinator boundary
- SSE bytes emitted and event count
- abort latency from cancel call to terminal stream event

Initial success targets for this slice:

- request translation remains sub-5 ms in unit-test scale
- SSE ordering is deterministic for all tested event sequences
- abort completes within one worker-stream round in tests
- no more than one active request is admitted at a time

If a probe cannot be measured in this slice, the metrics report must mark it as `N/A` with a reason.

## Verification Plan

Targeted verification:

```bash
swift test --package-path services/control-plane-swift --filter HTTPGatewayTests
```

Broader verification after implementation:

```bash
make swift-test
make coverage
```

## Exit Conditions

Task 4 is complete when:

- HTTP gateway tests pass
- control-plane regression tests still pass
- the request coordinator can reject or cancel requests deterministically
- `GET /v1/models` returns current catalog state
- the metrics report includes coverage plus Task 4 path timing notes
