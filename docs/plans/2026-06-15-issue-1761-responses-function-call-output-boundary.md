# Responses Function Call Output Boundary Plan

## Goal

Add a focused untrusted-context boundary for OpenAI Responses `function_call_output`
input items. A Responses follow-up can carry tool output as item data rather than
as a chat-style `tool` or `functions.*` message; Melix should preserve that data
as prompt context while recording a boundary receipt that treats it as untrusted
tool output.

## Scope

- Decode and encode Responses `input` arrays that contain message items and
  `function_call_output` items.
- Normalize `function_call_output` items into internal text messages with
  `role = tool`, `name = call_id`, and the item `output` as message content.
- Keep prompt-context receipts receipt-only: record source type, source id,
  source field, role, policy, and boundary status without copying raw output.
- Preserve the existing string-input and message-array Responses behavior.

## Out of Scope

- Executing tools or validating that a `call_id` corresponds to an earlier model
  call.
- Changing worker protobuf payloads or generated protocol artifacts.
- Supporting every Responses item type in one broad PR.
- Claiming prompt injection is solved by receipt metadata alone.

## Architecture

`OpenAIResponsesRequest.Input` remains the request-level entry point. Its array
decoder will first accept the existing chat message shape and then accept a
typed Responses item shape for `function_call_output`. The normalizer maps that
item into the already-supported internal tool-output role, so
`PromptContextBoundaryReceipts` can reuse the existing `tool_output` policy and
source-id logic.

## Performance Probes and Metrics

This is a control-plane request-admission/codecs change. The relevant metrics are
the focused Swift test runtime, changed-line coverage, and the existing
PR-scoped performance workflow. No new runtime metric is added because the
change does not execute tools or introduce a production sampling path.

Success metrics:

- Focused Swift tests for Responses codecs and prompt-context receipts pass.
- Changed-line coverage for touched Swift source/test lines is at least 95%.
- Full local pre-commit gate passes on this 128 GiB+ macOS host.
- PR scoped performance report reaches `Status: ok` with `Regressions: 0`.

## Implementation Steps

1. Add a failing Swift contract test that decodes a Responses `input` array with
   a `function_call_output` item and asserts normalization to a `tool` message
   with `name = call_id`.
2. Add receipt assertions for the same request: the receipt must classify the
   segment as `tool_output`, include the call id as `source_id`, preserve
   `message_role = tool`, and omit raw output text.
3. Extend the Responses input array decoder/encoder with a typed item enum that
   preserves existing chat message encoding.
4. Update the unified runtime contract to describe the receipt-only
   `function_call_output` boundary.
5. Run focused tests, changed-line coverage, full local pre-commit gate, and
   remote PR checks/performance before merge.
