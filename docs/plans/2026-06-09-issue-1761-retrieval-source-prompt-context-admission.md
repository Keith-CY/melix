# Issue 1761 Retrieval Source Prompt Context Admission Plan

## Goal

Route deterministic retrieval source receipts for `text_search` and
`image_search` through the shared Python worker prompt-context admission
primitive without changing emitted observation payloads, replay fingerprints,
receipt JSON fields, or owner-scope evidence.

## Scope

This slice covers:

- source-specific `retrieved_document` receipts for deterministic `text_search`
  results;
- source-specific `retrieved_image` receipts for deterministic `image_search`
  results;
- the governing unified agentic tool runtime contract.

This slice does not add live RAG stores, skill entrypoints, memory entrypoints,
background-continuation admission, chat final projection checks, or new
owner-scope behavior. It preserves the caller-provided source receipt attachment
path added for tool observations.

## Architecture

The retrieval adapters already know the sanitized selected result payload, its
source id, result index, and whether owner scope was configured. That is enough
to express each selected result as one `PromptContextSegment`:

- `segment_id = <tool_call_id>:result-<1-based index>`
- `source_type = retrieved_document|retrieved_image`
- `source_field = results[<0-based index>]`
- `source_id = <selected corpus id or deterministic fallback>`
- `owner_scope_checked = <owner scope configured for this run>`

`admit_prompt_context_segments` then builds the stable
`melix.untrusted_context_receipt.v1` receipt without copying raw retrieved
text, captions, media refs, queries, or tool arguments into the receipt. The
adapter still stores the selected result values in the normal observation
payload, and `ToolObservationRecord` still attaches the source receipts beside
the generic `tool_observation` receipt.

## Performance Probes And Metrics

The changed path builds one `PromptContextSegment` and one source receipt per
selected deterministic retrieval result. Runtime cost remains linear in the
already-selected result count and does not add model inference, retrieval IO,
payload hashing, or result filtering work.

Verification must include:

- a focused failing test proving retrieval source receipts are generated
  through `admit_prompt_context_segments`;
- focused text/image retrieval source receipt tests;
- full `test_agentic_tools.py`;
- changed-line coverage for the touched Python scope with at least 95 percent
  changed-line coverage;
- local pre-commit gate on this host;
- PR-scoped performance report with `Status: ok`, regressions `0`, context
  regressions `0`, and verification failures `0`.

## Implementation Steps

1. Add a focused monkeypatch regression test that replaces
   `worker.runtime.agentic_tools.admit_prompt_context_segments` and proves
   selected text and image retrieval results become `PromptContextSegment`
   values with the expected segment metadata, source ids, owner-scope flags,
   and sanitized result values.
2. Update `worker.runtime.agentic_tools` to import `PromptContextSegment` and
   `admit_prompt_context_segments` from `worker.runtime.prompt_context`.
3. Replace `_retrieval_result_receipt` direct receipt construction with a
   prompt-context admission over one retrieval result segment and return the
   admitted receipt.
4. Update `docs/unified-agentic-tool-runtime-contract.md` so the retrieval
   source slice names `worker.runtime.prompt_context` as the receipt generation
   primitive.
5. Run focused tests, changed-line coverage, full local gate, and scoped
   performance before committing.

## Success Criteria

- Retrieval source receipts for text and image search are produced through
  `admit_prompt_context_segments`.
- Existing observation JSON shape, receipt fields, owner-scope flags, payload
  redaction, replay hashes, timeout metadata, and byte metrics remain
  unchanged.
- Receipt evidence still omits retrieved text, captions, media refs, queries,
  tool arguments, and private prompt text.
- The contract clearly states that deterministic retrieval source evidence uses
  the shared prompt-context admission primitive while broader RAG, skill,
  memory, background, and final prompt projection checks remain later #1761
  work.
