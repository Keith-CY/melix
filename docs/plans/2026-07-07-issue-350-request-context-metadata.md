# Issue 350 Request Context Metadata Follow-Up Plan

## Goal

Populate request-side context metadata before text generation reaches
`RequestCoordinator`, so the memory-aware serving admission receipt uses the
admitted request budget instead of falling back to model maximum context or the
repository default cap.

## Scope

In scope:

- Derive a bounded request context budget from the existing prompt-budget
  admission inputs.
- Attach stable `melix.gateway.*` context metadata to accepted OpenAI-compatible
  text requests before translation.
- Preserve `max_tokens` and `max_completion_tokens` as output caps, not context
  windows.
- Add focused tests proving the metadata reaches worker request execution
  metadata and drives the existing memory admission receipt.
- Document the follow-up contract and local verification evidence.

Out of scope:

- Changing protobuf schemas or worker request fields.
- Changing sampler, KV allocation, model loading, or worker decode behavior.
- Replacing the heuristic prompt token estimator.
- Measuring actual load-time OOM reduction.

## Architecture

`OpenAIHandler` already resolves the model, computes prompt-budget admission,
and then calls `ChatRequestTranslator`. This slice reuses that boundary. After
prompt-budget admission accepts a request, the handler derives:

- the model context window;
- the selected output cap;
- the heuristic prompt token estimate;
- the existing prompt-budget slack.

It then emits a request context budget through `NormalizedTextRequest` OpenAI
compatibility receipts. `ChatRequestTranslator` already merges those receipts
into `GenerateRequest.execution.ext`, and `RequestCoordinator` already consumes
`melix.gateway.context_length` and `melix.gateway.requested_context` when it
builds `melix.serving.memory_admission.*`.

The budget is clamped to the model context window and should represent the
estimated admitted request footprint:

```text
min(model_context_window, prompt_tokens_estimated + output_cap_tokens + slack)
```

This keeps output caps distinct from context windows while avoiding a default
"use the full model window" admission for short prompts on long-context models.

## Metadata Contract

Producer metadata:

- `melix.gateway.context_length`
- `melix.gateway.requested_context`
- `melix.gateway.context_source`
- `melix.gateway.context_window_tokens`
- `melix.gateway.prompt_tokens_estimated`
- `melix.gateway.prompt_tokens_estimate_source`
- `melix.gateway.prompt_tokens_estimate_slack`
- `melix.gateway.output_cap_tokens`

`context_length` and `requested_context` intentionally carry the same value in
this slice because the existing downstream receipt consumes either key as the
operator-requested context input. Extra fields are diagnostic provenance only.

## Test Plan

Follow TDD:

1. Add a RED `OpenAIHandlerTests` acceptance test proving an accepted
   long-context request writes gateway context metadata to worker execution
   metadata and that the memory admission receipt uses the same requested
   context value.
2. Add a RED focused unit test for the budget calculation, including that output
   caps do not become the context window.
3. Implement the budget helper and handler wiring.
4. Run focused Swift tests for prompt-budget and request metadata behavior.

Focused verification:

```bash
xcrun swift test --no-parallel --package-path services/control-plane-swift --filter OpenAIHandlerTests/gatewayContextMetadataFeedsMemoryAdmissionForAcceptedTextRequests
xcrun swift test --no-parallel --package-path services/control-plane-swift --filter OpenAIHandlerTests/maxCompletionTokensRemainsAnOutputCapInPromptBudgetAdmission
```

Pre-PR verification:

```bash
make bootstrap
make proto
make swift-test
make py-test
make integration-test
git diff --check
.githooks/pre-commit
```

## Performance And Metrics

The changed path performs existing prompt-budget arithmetic once for accepted
requests and adds constant-size string metadata. No model probe, load, memory
query, or worker call is introduced.

Success metrics:

- Focused handler tests pass.
- Changed Swift test scope passes under `xcrun swift test`.
- PR-scoped performance report status is `ok` with regressions `0` and
  verification failures `0`.

## Local Verification Evidence

Completed on 2026-07-07:

```bash
xcrun swift test --no-parallel --package-path services/control-plane-swift --filter TextEndpointContractTests/gatewayRequestContextBudgetKeepsOutputCapsDistinctFromContextWindows
xcrun swift test --no-parallel --package-path services/control-plane-swift --filter OpenAIHandlerTests/gatewayContextMetadataFeedsMemoryAdmissionForAcceptedTextRequests
xcrun swift test --no-parallel --package-path services/control-plane-swift --filter OpenAIHandlerTests/maxCompletionTokensRemainsAnOutputCapInPromptBudgetAdmission
xcrun swift test --no-parallel --package-path services/control-plane-swift --filter OpenAIHandlerTests/longContextAdmissionStillRejectsPromptsBeyondEstimateSlack
make bootstrap
make proto
make swift-test
make py-test
make integration-test
git diff --check
.githooks/pre-commit
```

Results:

- Gateway request-context budget contract test passed.
- Accepted OpenAI text request metadata feeds the memory admission receipt.
- Existing max-completion-token prompt-budget semantics still pass.
- Existing long-context over-budget rejection still passes.
- `make bootstrap` passed and configured the versioned git hooks path.
- `make proto` passed with no schema-generated artifact drift.
- `make swift-test` passed for the Swift protocol, worker, control-plane, and
  macOS menu bar packages.
- `make py-test` passed with 4728 passed, 14 skipped, and 2 warnings.
- `make integration-test` passed with 123 passed and 1 skipped.
- `git diff --check` passed.
- `.githooks/pre-commit` passed. It reran `make swift-test`, `make py-test`,
  and `make integration-test`; the scoped performance report status was `ok`
  with 0 selected probes, 0 regressions, and 0 verification failures.

Performance report:

```text
.runtime/pre-commit-performance/20260707-021858-c34f2042/report/report.md
```
