# Issue 1761 Harmony Recipient Tool Output Receipts

## Goal

Classify Harmony/Responses messages with `recipient = functions.<name>` as
untrusted tool output in control-plane prompt boundary receipts, and use that
recipient as receipt source metadata when no message `name` is present.

## Scope

This slice is limited to control-plane prompt-context receipt metadata:

- keep existing `tool`, `function`, and `functions.*` role classification as
  `tool_output`
- classify non-developer/non-system messages whose Harmony metadata recipient
  is `functions.*` as `tool_output`
- preserve the raw message role in receipt `message_role`
- emit `source_id` from the normalized message `name` when present, otherwise
  from the request-local Harmony recipient metadata when it identifies a tool
  target
- keep raw message content, tool arguments, private prompt text, media URIs, and
  media bytes out of `melix.prompt_context.receipts_json`

Out of scope:

- changing worker message roles or message payloads
- parsing tool arguments, tool call JSON, or Harmony channels
- changing tool-parser behavior
- adding owner-scope validation for tool output
- wiring new durable RAG, skill, memory, MCP, agent, workflow, or local-job
  entrypoints

## Architecture

`PromptContextBoundaryReceipts` owns request-local prompt receipt
classification immediately before the worker `GenerateRequest` is emitted. It
already sees each `NormalizedTextMessage`, including the optional Harmony
metadata captured by the Responses adapter. This slice keeps the classification
in that component: the receipt source type checks both normalized role and
normalized Harmony recipient, and `source_id` remains redacted source metadata
selected from already-normalized fields.

The worker request remains unchanged. The added receipt metadata is evidence
for downstream auditing only; it does not alter prompt content, cache scope, or
tool parser selection.

## Performance Probes

The changed path adds one optional recipient normalization and one prefix check
per non-system/non-developer message while building request-local receipt
evidence. It adds no filesystem access, networking, JSON parsing beyond the
existing receipt serialization, model execution, or parser work.

Success metrics:

- focused `ToolParserRegistryTests` pass
- Swift changed-line coverage for the touched source/test scope is at least 95
  percent
- the local pre-commit scoped performance report has status `ok`, zero
  regressions, zero context regressions, and zero verification failures
- the PR-scoped performance report has status `ok`, zero regressions, zero
  context regressions, and zero verification failures

## Verification Plan

1. Add a RED Swift test proving an assistant Harmony message with
   `recipient = functions.get_weather` records `source_type = tool_output`,
   `message_role = assistant`, and `source_id = functions.get_weather` without
   leaking the raw tool-call JSON.
2. Implement the minimal classifier and source-id fallback in
   `PromptContextBoundaryReceipts`.
3. Update `docs/unified-agentic-tool-runtime-contract.md` to document recipient
   classification and `source_id` fallback behavior.
4. Run focused Swift tests and changed-line coverage for the touched Swift
   scope.
5. Run `git diff --check`, the full pre-commit gate, and the PR evidence
   validator before opening the pull request.
