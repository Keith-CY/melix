# Issue 1384 Stream Liveness Conformance Slice

**Issue:** #1384

**Goal:** Add a narrow OpenAI-compatible conformance matrix slice proving that
worker heartbeat events are exposed as parseable SSE heartbeat envelopes, not as
comment-only keepalives or unstructured transport noise.

## Scope

This slice covers only the deterministic Swift control-plane boundary:

- `/v1/chat/completions` streaming responses backed by the in-process
  `RecordingConformanceWorker` fixture.
- Worker `heartbeat` events encoded by `SSEStreamWriter`.
- Machine-readable `OpenAIConformanceReport` rows for the heartbeat contract.

It does not change live socket behavior, add idle timers, implement stall
receipts, or add cancellation cleanup receipts. Those remain follow-up #1384
stream-liveness slices.

## Expected Contract

- A worker heartbeat event becomes an SSE record with `event: heartbeat`.
- The heartbeat record `data` is valid JSON containing the stable request id and
  heartbeat timestamp fields.
- Heartbeat data does not appear as an unnamed OpenAI data chunk.
- Token, heartbeat, terminal completion, optional usage, and `[DONE]` ordering
  remains deterministic for the fixture.

## Verification

Focused:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter OpenAIConformanceMatrixTests
git diff --check
```

Coverage:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter OpenAIConformanceMatrixTests
```

Metrics:

This is a conformance-test/documentation slice. If the repository scoped
performance selector does not select a direct probe, report metrics as
`N/A: conformance coverage only`.
