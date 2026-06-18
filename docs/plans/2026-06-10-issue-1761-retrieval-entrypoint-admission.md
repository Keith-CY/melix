# Issue 1761 Retrieval Entrypoint Admission Plan

## Goal

Wire the deterministic retrieval and local visit entrypoints through the Python
worker retrieval-context admission primitive before their redacted source
evidence is projected into tool-observation prompt context.

## Scope

This slice covers:

- `worker.runtime.retrieval_context` support for entrypoint-local receipt
  location fields while preserving the default retrieved document/image
  admission API.
- `worker.runtime.agentic_tools` text search, image search, and visit source
  receipt generation using the retrieval-context primitive instead of building
  retrieved document/image prompt-context receipts directly.
- Focused Python tests proving the concrete entrypoints call the retrieval
  admission primitive and keep existing receipt shape for text/image results
  and visited documents.
- A contract update clarifying that retrieval helpers are the required boundary
  for deterministic retrieval, live RAG, and local source integration
  entrypoints.

This slice does not implement a live RAG store, vector index, retrieval ranking,
document ingestion, session memory wiring, or new owner-scope lookup. Existing
deterministic owner-scope checks remain the source of `owner_scope_checked`.

## Best End-State Architecture

Retrieved documents, retrieved images, and visited local documents are
untrusted prompt context. Concrete retrieval entrypoints should perform any
owner-scope checks, redact evidence, and then call a source-specific admission
primitive that validates the source identifier, payload object, and
owner-scope metadata before emitting receipts.

The retrieval-context primitive remains the reusable source-specific boundary.
Its default output is stable for future live stores, while concrete result-list
and visit surfaces may provide entrypoint-local `segment_id`, `source_field`,
`reason`, and `corrective_action` values so existing receipt locations remain
stable for callers.

## Performance Probes And Metrics

The changed path adds one Python function call and small string validation per
emitted retrieval source receipt. It does not add filesystem scanning, model
inference, vector search, hashing, network calls, or scheduler work.

Verification must include:

- a red/green run for the focused `test_agentic_tools.py` and
  `test_retrieval_context.py` cases;
- adjacent prompt-context and tool-observation regression tests;
- changed-line coverage for the touched Python files at 95 percent or higher;
- full local pre-commit gate before commit on this host;
- PR-scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`.

## Implementation Steps

1. Add failing tests in `services/mlx-worker-python/tests/test_retrieval_context.py`
   showing retrieved document/image admission accepts entrypoint-local receipt
   fields and still emits redacted source receipts.
2. Replace the existing agentic-tools source admission test with a failing test
   proving text search, image search, and visit call
   `admit_retrieved_document_context` or `admit_retrieved_image_context` with
   the concrete `segment_id`, `source_field`, reason, corrective action,
   source ID, payload, and owner-scope flag.
3. Extend `PromptContextSourceEvidence` and `retrieval_context` minimally so
   default callers preserve the existing helper output while entrypoint callers
   can override receipt location and reason text.
4. Route `agentic_tools._retrieval_result_receipt` and
   `agentic_tools._visit_document_receipt` through the retrieval-context
   helper, preserving the public receipt JSON asserted by existing tests.
5. Update `docs/unified-agentic-tool-runtime-contract.md` to record this
   concrete deterministic retrieval/local-source wiring.
6. Run focused tests, adjacent tests, changed-line coverage, full local gate,
   and PR-scoped performance checks before opening the PR.

## Success Criteria

- Text search, image search, fixture visit, and workspace-file visit retrieved
  source receipts are emitted through `worker.runtime.retrieval_context`.
- Existing receipt shape remains stable for deterministic result and visit
  surfaces.
- Source receipts still omit raw retrieved text, captions, media refs, local
  paths, and page content.
- Malformed retrieval helper inputs continue to produce refusal receipts with
  no admitted user payload.
