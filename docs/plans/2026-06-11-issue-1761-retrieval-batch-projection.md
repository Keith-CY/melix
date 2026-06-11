# Issue 1761 Retrieval Batch Projection Plan

## Goal

Add a side-effect-free Python worker helper for projecting multiple
already-redacted retrieved document and retrieved image entries into one
user-role prompt payload while preserving untrusted-context receipts.

## Scope

This slice covers:

- `worker.runtime.retrieval_context` batch projection for ordered retrieved
  document/image entries.
- Focused tests proving valid sibling entries survive malformed entries,
  duplicate prompt payload fields fail closed before overwrite, and unknown
  retrieval context kinds produce refusal receipts.
- `docs/unified-agentic-tool-runtime-contract.md` documentation for retrieval
  batch projection.

This slice does not implement retrieval storage, ranking, indexing, ingestion,
live RAG, session wiring, local-source discovery, or owner-scope lookup.
Callers must continue to pass already-redacted payload dictionaries and
source-specific owner-scope decisions.

## Best End-State Architecture

Future live RAG, document retrieval, image retrieval, and local source
integration surfaces should be able to admit ordered source evidence without
manually merging prompt payload dictionaries or stitching receipts together.
The batch helper should delegate every item to the existing single-entry
retrieval admission primitives, copy admitted receipts, and isolate invalid
items into refusal receipts without dropping valid siblings.

Duplicate prompt payload fields are a security-sensitive merge failure because
blind dictionary updates can silently replace earlier admitted source evidence.
The helper must preserve the first admitted entry, refuse later duplicates, and
record a machine-readable refusal receipt with a `duplicate_*_context_field`
reason. Concrete callers that project result lists should use stable unique
`source_field` values such as `retrieved_document_0` or `retrieved_image_0`.

## Performance Probes And Metrics

Runtime cost is linear in the number of already-redacted entries. The helper
adds small metadata validation and dictionary membership checks only; it must
not add filesystem scanning, vector search, model inference, hashing, network
access, or scheduler work.

Verification must include:

- red/green focused tests in `test_retrieval_context.py`;
- adjacent prompt-context and agentic-tool retrieval regression tests;
- changed-line coverage for `worker.runtime.retrieval_context` at 95 percent
  or higher;
- PR-scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`;
- full local pre-commit gate before commit on this host.

## Implementation Steps

1. Add tests for `RetrievalContextEntry` and
   `project_retrieval_contexts`:
   - multiple document/image entries are admitted into one prompt payload;
   - admitted receipts are copied and omit raw retrieved text or captions.
2. Add tests for malformed and duplicate entries:
   - malformed entries produce copied refusal receipts while valid siblings are
     preserved;
   - duplicate `source_field` values fail closed with
     `duplicate_retrieved_document_context_field` or
     `duplicate_retrieved_image_context_field` before overwriting;
   - unknown retrieval context kinds are refused.
3. Implement the dataclasses and projection helper in
   `worker.runtime.retrieval_context` by delegating to
   `admit_retrieved_document_context` and `admit_retrieved_image_context`.
4. Update the unified runtime contract with the projection behavior and caller
   expectations.
5. Run focused tests, adjacent tests, changed-line coverage, performance
   report, and the full local gate before opening a PR.

## Success Criteria

- Future retrieval callers can project multiple already-redacted source
  entries without ad hoc dictionary merges.
- Malformed retrieved document/image entries are isolated into refusal
  receipts and do not suppress valid siblings.
- Duplicate prompt payload fields do not overwrite earlier admitted evidence.
- The helper remains a prompt-boundary primitive only and introduces no
  retrieval storage, ranking, indexing, ingestion, live RAG, or session wiring.
