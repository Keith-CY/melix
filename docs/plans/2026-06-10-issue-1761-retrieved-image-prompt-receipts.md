# Issue 1761 Retrieved Image Prompt Receipt Classification Plan

## Goal

Continue #1761 by making the live control-plane prompt-context receipt path
classify retrieved image and RAG image message sources with source-specific
`retrieved_image` boundary evidence.

## Scope

This slice covers the existing Swift `PromptContextBoundaryReceipts` helper
used by `ChatRequestTranslator` before `Melix_Worker_V1_GenerateRequest`
messages are sent to a worker.

In scope:

- classify request-local message names such as `retrieved_image-*`,
  `retrieved-image-*`, `image_retrieval-*`, `rag_image-*`, and
  `rag-image-*` as `source_type = retrieved_image`;
- emit retrieved-image-specific `reason` and `corrective_action` text;
- keep raw image captions, media URIs, byte payloads, prompt text, and private
  source payloads out of receipt JSON;
- update the unified runtime contract to document the live retrieved-image
  classification.

Out of scope:

- implementing a RAG store, image index, image retrieval ranking, or owner
  lookup;
- changing prompt message roles, names, parts, cache fingerprints, or worker
  protobuf schema;
- changing deterministic Python retrieval-source receipts.

## Best End-State Architecture

Prompt receipt classification should cover both textual and visual retrieved
context before prompt messages cross into the worker. Live image retrieval
stores can later perform owner-scope and admission/refusal checks before
constructing messages, while this control-plane receipt remains the final
request-translation evidence that retrieved image prompt data is untrusted.

The classification must be based only on request-local metadata already present
at prompt assembly time: message role and normalized message `name`. It must
not parse message content or inspect image payloads.

## Performance Probes And Metrics

The changed path remains a single linear pass over already-shaped messages and
parts. The new classification adds a constant-time prefix check per named
message and no filesystem IO, model inference, vector search, hashing, or
scheduler work.

Verification must include:

- focused Swift test coverage for retrieved-image prompt receipt
  classification;
- changed-line coverage for the touched Swift source and test file with at
  least 95 percent coverage;
- full local pre-commit gate before commit on this host;
- PR-scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`.

## Implementation Steps

1. Add a failing Swift test that sends live prompt messages named with
   retrieved-image and RAG-image prefixes and expects `retrieved_image`
   receipts.
2. Assert retrieved image receipts preserve `source_id`, stay `included =
   true`, keep `owner_scope_checked = false`, and omit raw prompt/media text
   from receipt JSON.
3. Extend `PromptContextBoundaryReceipts.sourceType(for:)` and
   `sourcePolicy(for:)` for retrieved-image source names.
4. Update `docs/unified-agentic-tool-runtime-contract.md` with the new live
   source classification and policy text.
5. Run focused Swift tests, changed-line coverage, full local gate, and PR
   scoped performance checks before opening the PR.

## Success Criteria

- Live translated chat requests classify retrieved image prompt sources as
  `source_type = retrieved_image`.
- Retrieved-image receipt policy matches the existing Python retrieval prompt
  policy language.
- Receipt JSON remains redacted and does not include raw caption, media URI,
  media bytes, prompt text, or private source payloads.
- Existing retrieved-document, skill, memory, background, tool-output, generic
  chat, and assistant-history receipt behavior remains unchanged.
