# Issue 1761 Rerank Document Boundary Receipts

## Goal

Wire one live retrieval-adjacent HTTP endpoint into the untrusted-context
receipt contract by attaching redacted boundary receipts for `/v1/rerank`
candidate documents.

## Scope

This slice covers the Swift control-plane OpenAI-compatible `/v1/rerank`
handler. It records response-side boundary evidence for every candidate
document supplied in the request while preserving the worker request schema and
the raw document array sent to the rerank worker.

In scope:

- emit one `melix.untrusted_context_receipt.v1` receipt per request document;
- classify those receipts as `source_type = retrieved_document`;
- expose receipt metadata on the JSON rerank response without raw document
  text, query text, private prompt bodies, or source payloads;
- record small request-local metrics for the receipt count.

Out of scope:

- adding protobuf fields to `RerankRequest`;
- changing rerank scoring, top-k behavior, or worker request payloads;
- implementing a durable RAG store, document ingestion, indexing, owner lookup,
  or chat/session wiring;
- claiming the candidate document has passed cross-owner store validation.

## Best End-State Architecture

Live RAG and retrieval stores should eventually perform owner-scope checks,
redaction, and admission before evidence reaches a prompt or model endpoint.
That broader architecture still belongs in source-specific retrieval services
and Python worker admission primitives.

This slice is deliberately narrower: `/v1/rerank` already receives caller
supplied candidate documents and forwards them to a rerank worker. The control
plane should make that trust boundary visible to API consumers by returning
redacted data-only receipts. The receipts identify document indexes and
request-local source IDs, not document content.

## Performance Probes And Metrics

The changed path performs a linear pass over the already-decoded document list
and creates small Codable receipt structs. It does not add filesystem IO,
vector search, model inference, hashing, protobuf regeneration, or scheduler
work.

Verification must include:

- focused red/green Swift test for `/v1/rerank` receipt response fields;
- changed-scope coverage for the touched Swift source and test file with at
  least 95 percent coverage;
- full local pre-commit gate before commit on this host;
- PR-scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`.

Metrics:

- `rerank.prompt_context.receipt_count`

No registered PR-scoped probe currently targets this metadata-only path, so the
remote PR-scoped performance workflow remains the performance merge gate.

## Implementation Steps

1. Add a failing `OpenAIHandlerTests` case proving `/v1/rerank` responses expose
   redacted document boundary receipts while the worker request documents remain
   unchanged.
2. Add Codable response receipt structs and helper construction in
   `OpenAIHandler`.
3. Attach the receipts and schema marker to `OpenAIRerankResponse`.
4. Record `rerank.prompt_context.receipt_count`.
5. Update the unified agentic tool runtime contract with the endpoint-specific
   boundary note.
6. Run focused tests, changed-scope coverage, full local gate, and PR-scoped
   performance before merge.

## Success Criteria

- `/v1/rerank` responses include `untrusted_context_receipt_schema =
  melix.untrusted_context_receipt.v1`.
- `/v1/rerank` responses include one `untrusted_context_receipts` item per
  input document.
- Receipts use `source_type = retrieved_document`, `trust_level = untrusted`,
  `policy = data_only`, `boundary_checked = true`, and `included = true`.
- Receipts do not include raw candidate document text.
- Existing rerank worker dispatch, response scores, and request document
  forwarding remain unchanged.
