# Issue 1761 Function Role Tool Output Receipts

## Goal

Classify OpenAI-compatible legacy `function` role messages and Harmony-style
`functions.<name>` role messages as untrusted tool output when control-plane
prompt boundary receipts are built.

## Scope

This slice is limited to control-plane prompt-context receipt classification:

- keep existing `tool` role messages classified as `tool_output`
- add `function` and `functions.*` roles to the same `tool_output` trust
  boundary
- preserve redacted receipt JSON with no raw tool output text
- update the unified runtime contract to document the role aliases

Out of scope:

- changing worker message roles or prompt payloads
- adding new tool parser behavior
- parsing function names or tool-call arguments into receipts
- owner-scope validation for tool output

## Architecture

`PromptContextBoundaryReceipts` already owns control-plane classification for
prompt-adjacent message parts. Extend its role classifier so legacy function
outputs use the existing source policy, reason, corrective action, and receipt
shape for `tool_output`. This keeps the behavior local to evidence metadata and
does not alter the normalized messages sent to the worker.

## Performance Probes

The changed path adds two role string comparisons while building request-local
receipt evidence. It does not add filesystem access, network calls, model
execution, or parser work.

Success metrics:

- focused `ToolParserRegistryTests` pass
- Swift changed-line coverage for the touched source/test scope is at least 95
  percent
- scoped performance report has status `ok`, zero regressions, and zero
  verification failures

## Verification Plan

1. Add a RED Swift test covering `function` and `functions.get_weather` roles.
2. Implement the role classifier update in `PromptContextBoundaryReceipts`.
3. Update `docs/unified-agentic-tool-runtime-contract.md`.
4. Run focused Swift tests, changed-line coverage, pre-commit, and PR-scoped
   performance before opening the PR.
