# Issue 1384 JSON Schema Null Conformance Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for implementation. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pin the OpenAI-compatible boundary behavior for `response_format` requests that explicitly send `json_schema: null`.

**Architecture:** Keep the slice at the Swift control-plane conformance boundary described by ADR 0002. The existing `StructuredOutputRequestFormat` parser already treats a null `json_schema` as missing for `type: json_schema`; this slice records that behavior in the conformance matrix so future gateway or parser changes cannot accidentally dispatch an unenforceable structured-output request to a worker.

**Tech Stack:** Swift Testing, `OpenAIConformanceMatrixTests`, `OpenAIHandler`, `ChatRequestTranslator`, and the existing structured-output validation path.

---

## Scope

This slice covers a single OpenAI-compatible request-shape edge case:

- `/v1/chat/completions` receives `response_format: { "type": "json_schema", "json_schema": null }`.
- Melix returns a typed HTTP 400 compatibility error with `code=invalid_argument`.
- No worker generation request is dispatched.
- The conformance report records the row as passed.

This slice does not implement grammar-constrained decoding, change JSON-schema enforcement semantics, or add worker/runtime structured-output features. Those remain tracked by issue #2605 and broader issue #1384 follow-up slices.

## Success Metrics

- The focused `OpenAIConformanceMatrixTests` suite passes.
- The conformance report JSON contains the new `response_format.json_schema=null` row.
- The row proves typed rejection and no worker dispatch.
- Changed-scope coverage remains at or above the repository 95 percent requirement.
- PR-scoped performance report is `ok` with zero regressions before merge.

## Implementation Tasks

- [x] Add a red assertion in `OpenAIConformanceMatrixTests` requiring the conformance report JSON to contain `response_format.json_schema=null`.
- [x] Run the focused Swift test and confirm it fails because the row is not present.
- [x] Add a matrix row for `response_format.json_schema=null` that posts a chat-completions request with explicit null schema and asserts:
  - HTTP status `400`;
  - error `code` is `invalid_argument`;
  - error `field` is `response_format`;
  - error `phase` is `structured_output`;
  - no worker request was recorded.
- [x] Rerun the focused Swift test and confirm it passes.
- [x] Run repository verification before PR creation:
  - `make bootstrap`;
  - `make proto`;
  - `make swift-test`;
  - `make py-test`;
  - `make integration-test`;
  - pre-commit full gate and scoped performance report.

## Verification Commands

Focused red/green:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter OpenAIConformanceMatrixTests
```

Repository gate:

```bash
make bootstrap
make proto
make swift-test
make py-test
make integration-test
```

Pre-commit and scoped metrics:

```bash
.githooks/pre-commit
```

The scoped performance report must be `Status: ok`, with `Regressions: 0` and `Verification failures: 0`, before opening the PR.

## Known Deferred Work

- Full `response_format: json_schema` sampler enforcement remains issue #2605.
- Worker-side grammar-constrained decoding and tool-argument constrained generation are out of scope for this conformance-only PR.
- Additional `/v1/responses` and `/v1/messages` structured-output edge rows can reuse this pattern in later #1384 slices.
