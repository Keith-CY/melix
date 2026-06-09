# Chat Prompt Context Boundary Receipts

## Goal

Add a small control-plane prompt-boundary evidence slice for issue #1761 by
recording untrusted-context receipts for chat/request messages before they are
sent to the worker runtime.

## Scope

This slice covers the Swift `ChatRequestTranslator` path that turns
OpenAI-compatible Chat Completions, Completions, Responses, and Melix Messages
requests into `Melix_Worker_V1_GenerateRequest.messages`.

In scope:

- record one receipt per non-empty non-system/developer message part projected
  into the worker request
- store the receipt count and canonical JSON array in `execution.ext`
- keep the original message roles, content, media parts, and protocol schema
  unchanged
- update the unified agentic tool runtime contract to document this chat prompt
  assembly boundary

Out of scope:

- rewriting prompt text or changing chat-template behavior
- adding protobuf fields for receipts
- classifying operator-configured system or developer instructions as
  untrusted
- broader RAG store, skill, memory, and background continuation wiring

## Architecture

The new helper is Swift-local and mirrors the Python
`melix.untrusted_context_receipt.v1` shape so request evidence has the same
field names across the control plane and Python worker. It intentionally omits
raw prompt text and stores only segment identifiers, source type/field, message
role, trust policy, inclusion status, and corrective guidance.

`ChatRequestTranslator.translate(...)` builds the receipts after request
shaping and before assigning `generateRequest.messages`. This records the
boundary closest to the worker request without changing request shaping,
token-count estimation, media normalization, or cache fingerprints.

## Performance Probes

The changed path performs a fixed linear pass over already-shaped messages and
message parts. The output is a small JSON receipt array in `execution.ext`.
No registered PR-scoped probe currently targets this metadata-only path; the
PR-scoped performance workflow remains the remote gate. Local verification must
include changed-scope coverage for the touched Swift lines.

## Verification

- TDD red/green Swift test for `ChatRequestTranslator` receipt ext fields
- focused Swift test for the touched translator behavior
- changed-scope coverage for the touched Swift source and test file, target
  at least 95 percent
- `make bootstrap`
- `make proto`
- `.githooks/pre-commit` full local gate before commit
- PR-scoped performance report with status `ok` and zero regressions before
  merge

## Success Criteria

- Worker `GenerateRequest.execution.ext` includes:
  - `melix.prompt_context.receipt_schema =
    melix.untrusted_context_receipt.v1`
  - `melix.prompt_context.receipt_count`
  - `melix.prompt_context.receipts_json`
- Receipts include no raw prompt text, private tool arguments, or media URLs.
- System/developer messages are not marked as untrusted user data in this
  slice.
- Existing request translation behavior remains unchanged.
