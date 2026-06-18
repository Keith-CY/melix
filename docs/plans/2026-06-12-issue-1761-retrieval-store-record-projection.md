# Issue 1761 Retrieval Store Record Projection

## Goal

Add a side-effect-free retrieval store record projection bridge so future live
RAG, document, and image retrieval stores can hand already-redacted records to
the existing untrusted prompt-context receipt boundary without each store
reimplementing record shape validation.

## Scope

This slice is limited to the Python worker retrieval prompt-context boundary:

- add `worker.runtime.retrieval_context.project_retrieval_store_records`
- accept ordered record mappings for `retrieved_document` and `retrieved_image`
- validate the top-level record container and each record's `context_kind`
  before converting valid records to `RetrievalContextEntry`
- keep malformed records isolated in `refusal_receipts` so valid siblings still
  project into the prompt user payload
- update the unified runtime contract with the concrete future-store entrypoint
  guidance

Out of scope:

- live RAG store lookup, indexing, ranking, or hydration
- filesystem reads, media fetches, or local source ingestion
- owner inference or session mutation
- prompt wording changes or copying raw source text into receipts

## Architecture

The existing `RetrievalContextEntry` and `project_retrieval_contexts` helper
remain the canonical batch admission surface. The new helper is a thin bridge
from plain store records to those entries. It validates only the outer store
record shape and lets the existing single-entry admission helpers enforce
source ID, payload, owner-scope, duplicate-field, and entrypoint metadata
rules.

Malformed top-level containers fail closed with `source_field = records`.
Non-mapping records fail closed with `source_field = record`. Unsupported
`context_kind` values fail closed with `source_field = context_kind`.

## Performance Probes

The helper runs linear validation over an already-materialized list or tuple and
does not add filesystem or network work. The scoped performance gate should
select the existing prompt-context/retrieval-context probe set when applicable;
otherwise the metrics report may have zero selected probes and `Status: ok`.

Success metrics:

- focused retrieval-context tests pass
- changed-scope coverage for `retrieval_context.py` and
  `test_retrieval_context.py` is at least 95 percent
- scoped performance report has zero regressions and zero verification failures

## Verification Plan

1. Add RED tests for:
   - admitted document and image store records with redacted receipts
   - malformed top-level containers
   - non-mapping records and malformed records that do not drop valid siblings
   - unsupported `context_kind` using retrieved-document or retrieved-image
     fallback source IDs
2. Implement `project_retrieval_store_records`.
3. Run focused retrieval-context tests with coverage and changed-line coverage.
4. Run the repository gates required before commit and PR:
   - `git diff --check`
   - `make swift-test`
   - `make py-test`
   - `make integration-test`
   - scoped performance report
