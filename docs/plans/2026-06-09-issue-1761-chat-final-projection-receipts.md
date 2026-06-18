# Chat Final Projection Prompt Context Receipts

## Goal

Continue issue #1761 by classifying assistant/model final-answer content as its
own untrusted prompt-context source when prior model output is projected back
into a later worker request.

## Scope

This slice updates the Swift `PromptContextBoundaryReceipts` metadata path used
by `ChatRequestTranslator`. It does not alter prompt message content, message
roles, cache scope, worker protobuf fields, or persisted conversation payloads.

In scope:

- classify non-tool assistant message parts as `source_type =
  model_final_answer`
- preserve existing `tool` role classification as `tool_output`
- keep raw assistant text, tool output, media URIs, media bytes, and private
  prompt text out of receipt JSON
- document the new source-specific receipt class in the unified runtime
  contract

Out of scope:

- changing chat-template rendering or assistant transcript persistence
- adding owner-scope checks for background continuations, skills, memories, or
  live RAG stores
- adding protobuf fields for prompt receipts

## Performance Probes

The changed path is a constant-time branch in the existing linear prompt
receipt pass over shaped messages. The local and remote PR-scoped performance
reports remain the regression gate.

## Verification

1. Focused Swift test for `PromptContextBoundaryReceipts` source
   classification.
2. Changed-scope Swift coverage for the touched source and test scope, at least
   95 percent.
3. Full local pre-commit gate before commit on the macOS host.
4. Remote PR checks and PR-scoped performance report with status `ok` and zero
   regressions before merge.
