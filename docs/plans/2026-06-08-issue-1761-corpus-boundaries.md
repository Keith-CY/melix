# Issue 1761 Corpus Boundary Plan

## Goal

Extend the deterministic agentic tool untrusted-context boundary so malformed
retrieved text and image corpus containers or rows fail closed with typed
observations instead of being silently treated as empty retrieval results.

## Scope

This slice covers the Python worker deterministic agentic tool runtime:

- `text_search` fixture corpus container selection
- `image_search` fixture corpus container selection
- malformed retrieved corpus rows inside selected text and image corpora
- the governing agentic tool runtime contract

This slice does not cover owner-scoped retrieval, workspace path resolution,
prompt assembly wrappers, skill or memory entrypoints, or background-job
continuations. Those remain follow-up work under #1761.

## Architecture

The end-state boundary is a shared untrusted-value validation layer for every
retrieved segment before it can participate in tool execution or prompt
assembly. This slice keeps the boundary local to `_context_list(...)`, the
single helper used by deterministic text and image retrieval fixtures.

Malformed corpus state must fail closed and preserve evidence:

- reject non-list selected corpus containers
- reject non-object rows inside selected corpus lists
- emit `reason = invalid_untrusted_input_type`
- include `field`, `source_type`, `source_id`, `expected_type`,
  `actual_type`, and `corrective_action`
- preserve current successful retrieval behavior for valid corpus lists

## Performance Probes And Metrics

The changed path runs once per deterministic `text_search` or `image_search`
tool call. The overhead is bounded to `isinstance` checks over fixture rows
that are already iterated by the search adapters.

Verification will include:

- focused pytest for the new fail-closed corpus paths
- full `test_agentic_tools.py`
- changed-line coverage for modified Python files with a target of at least
  95 percent
- local PR-scoped performance report with `Status: ok`, regressions `0`, and
  verification failures `0`

If no registered PR-scoped performance probe is selected, the metrics report
will record that explicitly.

## Implementation Steps

1. Add failing tests in `services/mlx-worker-python/tests/test_agentic_tools.py`
   for:
   - a selected text corpus reference whose container is not a list
   - a selected image corpus row that is not a JSON object
2. Update `_context_list(...)` in
   `services/mlx-worker-python/worker/runtime/agentic_tools.py` to raise
   `AgenticToolRuntimeError` with typed invalid-untrusted details for those
   cases.
3. Keep successful `text_search` and `image_search` behavior unchanged for
   valid top-level lists and corpus-ref mappings.
4. Update `docs/unified-agentic-tool-runtime-contract.md` to state that corpus
   containers and rows fail closed.
5. Run focused tests, changed-line coverage, scoped performance, and PR gates
   before opening the PR.

## Success Criteria

- Non-list selected text or image corpus containers produce failed
  observations, not empty search results.
- Non-object text or image corpus rows produce failed observations, not
  silently filtered rows.
- Failed observations use the same typed `invalid_untrusted_input_type` receipt
  shape introduced by PR #1905.
- Existing valid retrieval fixture tests still pass.
