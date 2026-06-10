# Issue 1761 Live Source Policy Receipts Plan

## Goal

Continue #1761 by making the live control-plane chat prompt receipt path emit
source-specific data-only policy text for tool output, retrieved-document/RAG
data, skills, memories, background continuations, model-final-answer history,
and generic chat prompt messages.

## Scope

This slice covers the existing Swift `PromptContextBoundaryReceipts` helper
used by `ChatRequestTranslator` before it sends
`Melix_Worker_V1_GenerateRequest.messages` to the Python worker.

In scope:

- keep the existing source classification based on message role and normalized
  message `name`;
- emit source-specific `reason` and `corrective_action` fields for each
  source type;
- keep raw prompt text, media URIs, media bytes, tool arguments, and private
  prompt content out of receipt JSON;
- update the unified agentic tool runtime contract to document the live policy
  mapping.

Out of scope:

- implementing a RAG store, skill store, memory store, or background-job
  continuation store;
- changing prompt messages, roles, names, media parts, cache fingerprints, or
  chat-template behavior;
- adding protobuf fields or changing Python worker request schema.

## Best End-State Architecture

Every concrete prompt entrypoint should carry source-specific boundary evidence
closest to the point where untrusted content becomes model prompt data. For the
live chat translator, the best current source identifier is the already-shaped
message metadata: role plus optional `name`. This keeps classification
deterministic, avoids content parsing, and makes receipts useful to downstream
metrics without promoting source text into diagnostics.

The Swift helper should mirror the policy language already used by Python
prompt-context primitives. Later live RAG, skill, memory, and background
continuation stores can use their Python admission helpers before producing
messages; this Swift slice remains the final request-translation evidence
surface.

## Performance Probes And Metrics

The changed path still performs one linear pass over already-shaped messages
and message parts. The new policy lookup is constant time per emitted receipt
and does not add IO, retrieval, scheduler work, or model inference.

Verification must include:

- focused red/green Swift test for source-specific policy text;
- changed-line coverage for the touched Swift source and test file with at
  least 95 percent coverage;
- full local pre-commit gate on this host before commit;
- PR-scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`.

## Implementation Steps

1. Add a failing Swift test in `ToolParserRegistryTests` that builds a live
   translated text request with `tool`, RAG, skill, memory, background,
   assistant-history, and generic user message sources.
2. Assert each receipt keeps the existing `source_type`, `source_id`, and
   `included = true` metadata but uses source-specific `reason` and
   `corrective_action` values.
3. Implement a small policy lookup in `PromptContextBoundaryReceipts` keyed by
   the derived `source_type`.
4. Update `docs/unified-agentic-tool-runtime-contract.md` with the live
   source-specific policy mapping and clarify that this slice does not create
   stores.
5. Run focused Swift tests, changed-line coverage, full local gate, and
   PR-scoped performance before opening the pull request.

## Success Criteria

- Live translated chat requests expose source-specific prompt-boundary policy
  receipts for every supported source type.
- Receipt JSON still omits raw prompt content and media payloads.
- Existing message projection behavior is unchanged.
- Coverage and performance gates pass with no regression.
