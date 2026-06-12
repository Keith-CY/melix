# Issue 1761 Retrieval Lookup Result Projection

## Goal

Add a side-effect-free retrieval lookup-result projection bridge so future
durable RAG, document, and image lookup callers can attach already-redacted
retrieval results to user-role prompt context with stable untrusted-context
receipts.

## Scope

This slice is limited to the Python worker retrieval prompt-context boundary:

- add `worker.runtime.retrieval_context.project_retrieval_lookup_result`;
- accept lookup wrappers shaped as `{"records": <store records>}`;
- delegate record validation and receipt construction to
  `project_retrieval_store_records`;
- return copied prompt user payload, copied admitted receipts, copied refusal
  receipts, and an optional user-role lookup message;
- fail closed for malformed top-level lookup wrappers with a retrieval-lookup
  refusal receipt.

Out of scope:

- live RAG store lookup, indexing, ranking, hydration, or owner inference;
- filesystem reads, web fetches, media decoding, or session mutation;
- changing prompt wording or copying raw retrieved text/captions into receipt
  JSON.

## Architecture

`project_retrieval_store_records` remains the canonical bridge from plain
already-redacted retrieval records to `RetrievalContextEntry` admission. The new
lookup-result helper is a narrower wrapper adapter for callers that already have
an in-memory lookup result object. Valid wrappers delegate to the store-record
projection, then copy the returned payload and receipts before constructing a
single user-role lookup message. Malformed wrappers return no prompt payload and
one `source_type = retrieval_lookup` refusal receipt.

## Performance Probes And Metrics

The helper performs one `Mapping` check and delegates to the existing linear
store-record projection. It adds no filesystem access, network work, retrieval
ranking, model inference, or scheduler behavior.

Verification must include:

- focused red/green pytest runs for `test_retrieval_context.py`;
- changed-line coverage for touched Python files at 95 percent or higher;
- `git diff --check`;
- scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`;
- the required local gate before PR if the pre-commit hook requires it.

## Implementation Steps

1. Add failing tests for admitted lookup-result projection, malformed lookup
   wrappers, missing `records`, mixed valid/refused records, and defensive copy
   boundaries.
2. Implement `RetrievalLookupResultProjection` and
   `project_retrieval_lookup_result`.
3. Update `docs/unified-agentic-tool-runtime-contract.md` with the retrieval
   lookup-result contract.
4. Run focused tests, changed-line coverage, scoped performance, and the
   required local gate before opening the PR.

## Success Criteria

- Valid lookup wrappers produce one user-role lookup message with copied prompt
  payload and copied receipt metadata.
- Malformed wrappers produce no prompt payload, no admitted receipts, no lookup
  message, and one typed `retrieval_lookup` refusal receipt.
- Missing or malformed `records` delegate to the existing store-record refusal
  semantics.
- Refused records do not drop valid sibling retrieval results.
- Receipt JSON remains redacted from raw retrieved document text, image
  captions, media URIs, paths, and prompt bodies.
