# Remote Provider Usage-Only SSE Compatibility Plan

## Goal

Make OpenAI-compatible Remote Provider Chat accept the terminal usage-only SSE
chunk emitted by otherwise conforming providers, while retaining strict errors
for malformed completion payloads.

## Governing Contracts

- `CONTEXT.md` defines OpenAI Compatibility Conformance to include streaming
  chunk ordering and terminal-event behavior.
- `docs/plans/2026-07-31-remote-provider-desktop-chat.md` defines the direct
  Remote Provider Chat path and credential boundary.
- `docs/plans/2026-07-31-remote-provider-generation-control-parity.md` defines
  Remote Provider request passthrough and verification expectations.

## Reproduction Evidence

A credential-redacted live probe of the reported provider established that:

- `GET /models` returned HTTP 200 and advertised the requested model.
- A non-streaming chat completion returned HTTP 200 with one choice.
- A streaming chat completion returned normal delta and finish events, followed
  by a final JSON event containing `usage` and `choices: []`, then `[DONE]`.
- `parseSSEEvents` currently requests the first choice before reading usage, so
  the valid usage-only event raises `remote provider response did not include
  choices`.

No credential or raw provider response is retained as repository evidence.

## End-State Contract

1. An OpenAI-compatible streaming event with a non-empty first choice is parsed
   exactly as it is today.
2. A streaming event with no first choice is accepted only when it contains a
   valid `usage` object; it produces one usage event and parsing continues.
3. A streaming event with neither a first choice nor a valid usage object keeps
   the existing readable invalid-response error.
4. Non-streaming completion parsing remains strict and continues to require a
   non-empty choices array.
5. Token, usage, and completion event ordering remains deterministic.

## Performance And Success Metrics

- The parser remains linear in SSE event count and adds only a bounded dictionary
  lookup per event; no output-size-dependent allocation is introduced.
- The provider-shaped regression test fails before the implementation change and
  passes afterward.
- A negative streaming case proves that unrelated empty-choice events remain
  rejected.
- Changed-line coverage for the touched Swift scope is at least 95 percent.
- The repository test gate and scoped performance report complete without an
  in-scope regression.
- A credential-redacted live probe through the fixed client consumes the reported
  provider stream successfully.

## Delivery Slices

- [x] Reproduce and classify the provider response without persisting secrets.
- [x] Add provider-shaped positive and strict-negative regression coverage.
- [x] Implement usage-only SSE handling at the OpenAI-compatible parser boundary.
- [x] Run focused tests, changed-line coverage, full gates, and performance probes.
- [ ] Submit PR evidence and monitor review, CI, conflicts, and performance status.

## Verification Evidence

- The new provider-shaped test failed before the fix with `remote provider
  response did not include choices`.
- `swift test --package-path services/control-plane-swift --filter
  RemoteProviderClientTests`: passed, 25 tests.
- `swift test --package-path services/control-plane-swift
  --enable-code-coverage --filter RemoteProviderClientTests`: passed, 25 tests.
- `scripts/swift_changed_line_coverage.py`: 100.00 percent changed-line coverage
  for both the production parser (17/17) and its tests (71/71), 88/88 total.
- A temporary environment-keyed live test through
  `OpenAICompatibleRemoteProviderClient` observed non-empty assistant text, a
  usage event, and a completion event from the reported endpoint. The temporary
  test and its key were not retained.
- `make bootstrap`: passed.
- `make proto`: passed with no generated-artifact changes.
- `.githooks/pre-commit`: passed the full Swift gate, 5,480 Python tests
  (14 skipped), and 123 integration tests (1 skipped).
- The PR-scoped performance report status was `ok`: four changed files, zero
  selected registered probes, zero regressions, and zero verification failures.
  The parser change remains linear in SSE event count with one bounded usage
  lookup per event.
