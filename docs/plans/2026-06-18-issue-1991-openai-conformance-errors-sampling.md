# Issue 1991 OpenAI Conformance Error and Sampling Coverage Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for implementation. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the OpenAI conformance matrix so error-payload classes and sampling passthrough fields are proven at the Swift control-plane boundary.

**Architecture:** Keep the slice inside `OpenAIHandler` and `ChatRequestTranslator` where deterministic tests can post OpenAI chat payloads, inspect typed HTTP errors, and inspect translated worker `SamplingConfig`. Reuse the existing table-driven `OpenAIConformanceMatrixTests` and the existing prompt-budget admission path instead of adding a parallel harness.

**Tech Stack:** Swift Testing, `OpenAIHandler`, `ChatRequestTranslator`, `TextRequestShaper`, `ModelCatalog`, worker protobuf `SamplingConfig`, and the existing conformance report model.

---

## Scope

This PR implements issue #1991 as a child slice of the OpenAI conformance plan in `docs/plans/2026-05-24-issue-1384-openai-conformance-suite.md`:

- Add conformance rows for typed error payloads:
  - unsupported request field at the OpenAI boundary,
  - invalid schema at decode time,
  - backend unavailable before dispatch,
  - context overflow through prompt-budget admission.
- Add conformance coverage for sampling passthrough:
  - `seed` maps to worker sampling and compatibility receipts,
  - `frequency_penalty` maps to worker sampling and compatibility receipts.
- Preserve existing `max_tokens` and `max_completion_tokens` output-cap behavior.

This PR does not add real remote-provider proxy calls, backend token-logprob support, or new protobuf schemas.

## Success Metrics

- Matrix rows assert `code`, `field`, and `phase` for the new error classes where applicable.
- Error rows return before worker generation when the failure is pre-dispatch.
- `frequency_penalty` reaches `Melix_Worker_V1_SamplingConfig.frequencyPenalty`.
- `seed` and `frequency_penalty` are represented in `melix.generation.*` receipts.
- Changed-line coverage for touched Swift files is at least 95 percent.
- PR-scoped performance report is `ok` with no regression.

## Implementation Tasks

- [x] Add failing conformance rows in `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIConformanceMatrixTests.swift`.
  - Assert typed payload fields for unsupported field, invalid schema, worker unavailable, and prompt-budget context overflow.
  - Assert worker sampling and receipts for `seed` and `frequency_penalty`.
- [x] Extend request normalization for `frequency_penalty`.
  - Decode and encode `frequency_penalty` on OpenAI text-compatible request structs.
  - Carry it through `NormalizedTextRequest` and `ShapedTextRequest`.
  - Assign `GenerateRequest.sampling.frequencyPenalty` and receipt `melix.generation.frequency_penalty`.
- [x] Add typed error metadata without changing existing status codes.
  - Include `field` and `phase` in generation-bounds and decode errors.
  - Include `phase` in backend unavailable errors.
  - Include `field` and `phase` alongside prompt-budget metadata.
  - Reject explicitly unsupported OpenAI chat fields before worker dispatch.
- [x] Verify focused tests and changed-line coverage before full local gate.
  - `OpenAIConformanceMatrixTests`, `OpenAIHandlerTests`, and `TextEndpointContractTests` pass locally.
  - Swift changed-line coverage for the touched scope is `97.32%` (`254/261`).
- [x] Verify full local gate and PR-scoped performance before opening the PR.
  - `make swift-test` passes locally.
  - `make py-test` passes locally (`4066 passed, 14 skipped`).
  - `make integration-test` passes locally (`120 passed, 1 skipped`).
  - PR-scoped pre-commit performance report is `Status: ok` with `0` regressions.

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
