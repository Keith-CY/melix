# Issue 41 Structured Streaming And Reasoning Continuity

## Goal

Make shipped text streaming deterministic, request-scoped, reasoning-aware, tool-call-safe, and cache-friendly across Chat Completions, Completions, Responses, and Messages.

## Scope

- preserve raw generation text separately from display-cleaned text
- resolve reasoning controls through one shared policy path across shipped text endpoints
- assemble content, reasoning, and tool-call fragments with request-local parser state
- suppress incompatible tool parsing for JSON-only structured-output requests without explicit tools
- preserve hidden reasoning continuity for session follow-up turns without exposing hidden channels in operator-visible output
- expose stream-pipeline metrics and regression evidence

Out of scope:

- native Ollama `/api/*` routes
- new non-stream HTTP response behavior
- unrelated public output-shape changes

## Implementation Plan

1. Add regression tests for reasoning policy parity, structured-output gating, stream assembler isolation, replay-safe tool-call deltas, JSON reasoning-prefix cleanup, and hidden continuity sanitization.
2. Extend worker protobuf schema with raw text and parser observability fields, then regenerate Swift and Python protocol artifacts.
3. Add a Swift `ReasoningPolicyResolver` used by all shipped text request normalizers. Preserve top-level `enable_thinking`, `reasoning_effort`, Messages `thinking`, template kwargs, model/operator defaults, auto-detected family capability, and suppressions in deterministic precedence order.
4. Add request-scoped Python stream assembly that parses `raw_text || text`, emits unseen deltas only, separates content/reasoning/tool fragments, and skips recoverable malformed tool fragments.
5. Add session reasoning-continuity metadata in the control plane keyed by session/branch/request. Rehydrate supported follow-up turns through execution metadata/template kwargs while keeping raw hidden content out of SSE and public session state.
6. Add cache-scope/fingerprint metadata for reasoning mode, reasoning effort, parser mode, template kwargs, and continuity presence.
7. Update protocol docs and add a runbook covering the streaming/reasoning contract, probes, and acceptance metrics.

## Metrics And Success Targets

- `http.reasoning_mode_source.*` counts resolved policy sources.
- `http.reasoning_auto_detect_model_family.*` records auto-detected family decisions.
- `stream_pipeline.parser_state_bleed_count` remains zero in the 1,000-stream fixture.
- `stream_pipeline.malformed_tool_fragment_count` records recoverable skips without request failure.
- `stream_pipeline.duplicate_tool_delta_count` remains zero in sequential and parallel fixtures.
- `stream_pipeline.reasoning_leak_count` remains zero for structured-output and hidden-continuity fixtures.
- `stream_pipeline.continuity_rehydration_count` records supported repeated-turn rehydration.
- `stream_prefix_hold_chars` records the longest viable structural-prefix suffix held by a request-local assembler.
- `stream_short_reply_flush_count` records short visible prefixes emitted before a held structural suffix.

## Verification

- `make proto`
- `make swift-test`
- `make py-test`
- `make integration-test`
- touched-scope coverage commands for Swift request/SSE tests and Python stream assembler tests, targeting at least 95 percent coverage for changed scope

## Acceptance

- no cross-request parser-state bleed across the concurrency fixture
- no malformed or duplicated streamed tool-call payloads in repository-owned fixtures
- short visible streaming replies are not swallowed by marker-prefix buffering
- JSON-only structured-output streams are not contaminated by hidden reasoning prefixes or generic tool parsing
- repeated session turns preserve supported hidden reasoning continuity while public output remains sanitized
- metrics and docs explain how to reproduce the stream-pipeline evidence
