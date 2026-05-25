# Issue 1384 OpenAI Compatibility Conformance Suite Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for implementation. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make OpenAI-compatible request-shape, tool, reasoning/logprobs, and proxy model-routing behavior provable through a repository-owned conformance suite instead of scattered smoke tests.

**Architecture:** Keep this slice at the Swift control-plane boundary where Melix can deterministically prove compatibility without a real remote provider. The suite posts table-driven OpenAI chat payloads through `OpenAIHandler`, records the translated worker request and response boundary, and renders a machine-readable report from the same rows.

**Tech Stack:** Swift Testing, `OpenAIHandler`, `ChatRequestTranslator`, `TextRequestShaper`, `SSEStreamWriter`, existing worker protobuf fields, and `execution.ext` compatibility receipts.

---

## Scope

This PR implements the first issue #1384 conformance slice:

- `/v1/chat/completions` request-shape conformance for compatibility fields that often drift:
  - `max_completion_tokens`
  - conflicting `max_tokens` plus `max_completion_tokens`
  - `parallel_tool_calls=false`
  - legacy `functions`
  - legacy `function_call`
  - scalar and array `stop`
  - `logprobs` plus `top_logprobs`
  - per-request `model` routing through the active served-model roster
- Output boundary conformance for reasoning/tool/logprob-adjacent behavior:
  - streaming and non-streaming route the same request receipts
  - streaming tool-call deltas retain OpenAI-compatible chunk shape and terminal events
  - reasoning mode remains explicit in worker execution metadata
  - usage payloads carry completion token counts while logprob requests are explicitly marked unsupported at the request boundary
- A machine-readable report builder for the table rows so future CI or operator harnesses can write JSON artifacts without duplicating fixture logic.

This PR does not:

- implement third-party proxy network calls,
- add vendor-specific undocumented behavior,
- expand protobuf schemas,
- replace the separate SSE/prefill child issue #1392,
- claim worker-side token logprobs exist when the backend does not report them.

## Success Metrics

- Every row records `field`, `route`, `expected_behavior`, `observed_status`, and `observed_reason`.
- Accepted compatibility fields appear in typed worker fields or `execution.ext` receipts.
- Rejected compatibility fields return typed HTTP 400 and name the incompatible fields.
- Streaming and non-streaming fixture paths agree on the normalized request receipts.
- Proxy model routing row proves the inbound OpenAI `model` selects the served model dispatch handle.
- Changed-line coverage for the touched Swift scope is at least 95 percent.
- PR-scoped performance report is `ok` with no regression.

## Implementation Tasks

- [x] Add `OpenAIConformanceReport.swift` under `Sources/HTTPGateway/OpenAI/`.
  - Define `OpenAIConformanceRow`, `OpenAIConformanceObservedStatus`, and `OpenAIConformanceReport`.
  - Provide deterministic `jsonData()` and `jsonString()` helpers.
- [x] Add `OpenAIConformanceMatrixTests.swift` under `Tests/HTTPGatewayTests/`.
  - Write failing table rows for request shape, legacy tools, logprobs receipts, model routing, and report JSON.
  - Use a recording worker fixture local to the test file.
- [x] Extend `OpenAIChatCompletionsRequest`.
  - Decode/encode legacy `functions`, legacy `function_call`, `parallel_tool_calls`, `logprobs`, and `top_logprobs`.
  - Normalize legacy functions into the existing tool definition path.
  - Keep the existing typed HTTP rejection for conflicting `max_tokens` and `max_completion_tokens`.
- [x] Carry OpenAI compatibility receipts through `NormalizedTextRequest` and `ShapedTextRequest`.
  - Merge receipts into `GenerateRequest.execution.ext`.
  - Keep receipts empty for requests that do not include compatibility fields.
- [x] Add output boundary rows.
  - Confirm usage and reasoning execution metadata stay explicit.
  - Confirm streaming forced-tool fixtures emit OpenAI-compatible tool-call deltas.
  - Confirm logprobs request rows report `unsupported` instead of silently dropping the field.
- [x] Add protocol parity usage trailer and orphan tool-call markup cleanup rows.
  - Confirm chat-completions streaming usage is emitted as an OpenAI-compatible
    `chat.completion.chunk` trailer with empty `choices` and `usage` totals.
  - Confirm stream and non-stream chat-completions responses share cleanup for
    orphan `<tool_call>` and `<|tool_call>` markup so truncated tool markup does
    not leak into visible assistant text.
  - Keep this slice local to the Swift boundary; real proxy parity, Anthropic
    protocol parity, disabled-tool prompt guards, oversized payload truncation,
    and backend token logprobs remain follow-up work.
- [x] Verify focused tests, changed-line coverage, full local gate, and PR-scoped performance before opening the PR.

## Verification Commands

Focused:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter OpenAIConformanceMatrixTests
git diff --check
```

Pre-PR local gate:

```bash
make swift-test
make py-test
make integration-test
```

Metrics:

```bash
UV_PYTHON="${MELIX_PRE_COMMIT_UV_PYTHON:-${UV_PYTHON:-3.12}}" uv run --frozen --project services/mlx-worker-python --extra mlx python scripts/pre_commit_gate.py
```

The pre-commit gate writes the PR-scoped performance report under `.runtime/pre-commit-performance/`; the report must be `Status: ok` before PR creation.

## Known Deferred Work

- Issue #1392 remains the narrower SwiftLM-derived SSE/prefill-progress ordering slice.
- Real remote-provider proxy parity can reuse the report schema added here, but this PR only proves deterministic local request routing.
- Worker-generated token logprobs require runtime support and are intentionally represented as an explicit unsupported receipt in this slice.
- Anthropic/protocol parity, disabled-tool prompt guards, oversized payload
  truncation metadata, and backend token logprob propagation remain separate
  issue #1384 slices.
