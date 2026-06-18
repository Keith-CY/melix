# Issue 1761 Retrieval Context Admission Plan

## Goal

Add a small Python worker primitive that validates already-redacted retrieved
document and retrieved image evidence before future live RAG or source
retrieval entrypoints can project it into user-role prompt payloads.

## Scope

This slice covers:

- `worker.runtime.retrieval_context` as a reusable admission/refusal boundary
  for retrieved document and retrieved image prompt-context evidence.
- Focused Python tests for admitted retrieved document/image payloads,
  malformed-field refusal receipts, and reuse of the shared prompt-context
  source-evidence helper.
- `docs/unified-agentic-tool-runtime-contract.md` documentation for the
  retrieval-context primitive.

This slice does not implement a live RAG store, retrieval ranking, source
indexing, chat/session wiring, document ingestion, or owner-scope lookup.
Future callers must pass already-redacted payload dictionaries and perform
their own owner-scope checks before admission.

## Best End-State Architecture

Retrieved local documents, source snippets, images, and media metadata are
untrusted prompt context. Future RAG and source retrieval surfaces should call a
narrow admission helper with already-redacted evidence, receive a user-role
prompt payload, and attach receipt evidence that records the data-only boundary
without raw source content.

The helper belongs in the Python worker runtime beside `prompt_context`,
`tool_observation`, `background_continuation`, and `skill_memory_context`. It is
a prompt-boundary primitive, not a retrieval or storage layer. It delegates
admitted receipt creation to `admit_prompt_context_source_evidence` and refusal
receipt creation to `refused_source_prompt_context_receipt` so retrieved
document and image evidence uses the same source-specific receipt policy as
skills, memories, and background continuations.

## Performance Probes And Metrics

The changed path validates one small metadata dictionary and emits one receipt
per admitted retrieval payload. Runtime cost is constant per admitted source
payload and does not add filesystem scanning, vector search, model inference,
payload hashing, or scheduler work.

Verification must include:

- focused red/green tests for `test_retrieval_context.py`;
- adjacent prompt-context regression tests;
- changed-line coverage for the touched Python files with at least 95 percent
  coverage;
- full local pre-commit gate before commit on this host;
- PR-scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`.

## Implementation Steps

1. Add failing tests for `admit_retrieved_document_context` and
   `admit_retrieved_image_context`:
   - accepted payloads return `PromptContextAdmission.user_payload` with
     `retrieved_document` or `retrieved_image` fields;
   - receipts use `source_type = retrieved_document|retrieved_image` and omit
     raw evidence text;
   - monkeypatching `admit_prompt_context_source_evidence` proves the helper
     uses the shared prompt-context source-evidence primitive.
2. Add failing tests for malformed payload fields:
   - non-string source IDs, non-dict payloads, and non-boolean
     `owner_scope_checked` are refused before admission;
   - each refusal carries an `included=false` receipt with reason
     `invalid_retrieved_document_context_field` or
     `invalid_retrieved_image_context_field`.
3. Implement `worker.runtime.retrieval_context` with:
   - `RetrievalContextAdmissionError`;
   - `admit_retrieved_document_context(document_id, document_payload,
     owner_scope_checked)`;
   - `admit_retrieved_image_context(image_id, image_payload,
     owner_scope_checked)`;
   - deterministic `segment_id = <source_id>:retrieved-document-context` or
     `<source_id>:retrieved-image-context`;
   - source ID equal to the redacted document or image identifier.
4. Update the unified agentic tool runtime contract to specify this primitive
   as the required future admission boundary for live RAG and retrieved media
   prompt evidence.
5. Run focused tests, adjacent tests, changed-line coverage, full local gate,
   and PR-scoped performance before opening the PR.

## Success Criteria

- Retrieved document and image evidence can be admitted through reusable
  primitives before prompt projection.
- Refused malformed retrieval fields produce machine-readable refusal receipts
  and no user payload.
- Receipt evidence uses `melix.untrusted_context_receipt.v1`, records
  `source_type = retrieved_document|retrieved_image`, and omits raw source
  content.
- The implementation does not create a retrieval store or change existing
  deterministic tool, chat, or session behavior.
