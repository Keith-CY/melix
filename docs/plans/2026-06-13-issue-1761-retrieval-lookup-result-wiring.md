# Issue 1761 Retrieval Lookup Result Wiring

## Goal

Wire the deterministic text and image retrieval tool paths through
`worker.runtime.retrieval_context.project_retrieval_lookup_result` so concrete
retrieval observations and the side-effect-free lookup projection share the same
untrusted-context receipt boundary.

## Scope

This slice is limited to the Python worker deterministic agentic tool runtime:

- keep `text_search` and `image_search` payload shapes unchanged;
- build lookup-result records for selected text and image search results;
- derive source untrusted-context receipts from
  `project_retrieval_lookup_result`;
- keep `visit` on its direct retrieved-document admission path;
- update the unified runtime contract to document the concrete wiring.

Out of scope:

- live RAG store lookup, indexing, ranking, hydration, or owner inference;
- changing result ranking, corpus matching, or tool selection;
- changing prompt wording or copying raw retrieved text/captions into receipt
  JSON.

## Architecture

`agentic_tools.py` already normalizes deterministic `text_search` and
`image_search` fixture results before emitting observations. Those selected
results will now be converted into plain lookup records and passed through the
retrieval lookup projection helper. The returned admitted receipts are attached
to the existing tool observation payload under `_untrusted_context_receipts`;
the projection's prompt message is intentionally not emitted because the tool
observation already owns the user-visible payload.

`visit` remains separate because it represents a direct visited document payload
rather than a multi-result lookup wrapper.

## Performance Probes And Metrics

The wiring adds one small in-memory record list and a linear projection over the
already-selected results. It adds no filesystem access, network work, ranking,
model inference, or scheduler behavior.

Verification must include:

- focused red/green pytest runs for `test_agentic_tools.py`;
- changed-line coverage for touched Python files at 95 percent or higher;
- `git diff --check`;
- scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`;
- the required pre-commit local gate before pushing the PR.

## Implementation Steps

1. Add a failing test proving `text_search` and `image_search` pass selected
   results through `project_retrieval_lookup_result` with stable record fields.
2. Implement a narrow record builder and use the lookup projection receipts in
   both search payload helpers.
3. Update existing admission-wiring tests so `visit` still proves the direct
   admission path and retrieval search proves the lookup projection path.
4. Update `docs/unified-agentic-tool-runtime-contract.md`.
5. Run focused tests, coverage, diff checks, the scoped performance report, and
   the required local gate before opening the PR.

## Success Criteria

- `text_search` and `image_search` observations keep their current payload and
  receipt shapes.
- Selected search results are projected through
  `project_retrieval_lookup_result` before source receipts reach
  `normalize_tool_observation`.
- `visit` source receipts still use direct retrieved-document admission.
- Receipt JSON remains redacted from raw retrieved document text, image
  captions, media URIs, paths, and prompt bodies.
