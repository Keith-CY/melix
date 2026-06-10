# Issue 1761 Visit Source Receipts Plan

## Goal

Attach redacted source-specific untrusted-context receipts to successful
deterministic `visit` page/document observations.

## Scope

This slice covers the Python worker deterministic agentic tool runtime:

- fixture-backed `visit` pages that return page text
- workspace-local `visit` reads admitted by `WorkspacePathResolver`
- source receipts emitted alongside the existing generic tool-observation
  receipt
- the governing unified agentic tool runtime contract

This slice does not add a live network visit provider, durable RAG store,
session store wiring, skill store wiring, memory store wiring, or new owner
scope model. Missing pages, workspace path refusals, and unavailable workspace
files remain tool observations without an admitted retrieved-document source
receipt.

## Architecture

The deterministic `visit` adapter already returns text-bearing page extraction
payloads from fixture pages and workspace-local files. Those payloads can be
projected into agent traces as prompt data, so successful text-bearing
observations should carry the same redacted prompt-context receipt evidence
used by `text_search` retrieved documents.

The source receipt must describe the admitted document boundary without copying
page or file content into the receipt. The emitted payload remains unchanged so
existing replay fingerprints and downstream fixtures do not lose the extracted
page text. The source receipt is appended to the observation-level
`untrusted_context_receipts` list through the existing
`source_untrusted_context_receipts` path.

## Performance Probes And Metrics

The change adds one small receipt construction step only for successful
deterministic `visit` observations. No registered PR-scoped performance probe
is expected for this exact path, but the scoped performance report must still
show status `ok`, regressions `0`, context regressions `0`, and verification
failures `0`.

Verification will include:

- focused pytest for `visit` source receipts
- full `services/mlx-worker-python/tests/test_agentic_tools.py`
- changed-line coverage for the modified Python scope with at least 95 percent
  coverage
- local PR-scoped performance report with status `ok`

## Implementation Steps

1. Add a failing test proving fixture-backed `visit` success emits a redacted
   `retrieved_document` source receipt.
2. Add a second focused test proving workspace-local `visit` success emits the
   same source receipt while preserving `workspace_path_receipt`.
3. Route successful `visit` payloads through a shared source-receipt helper
   without changing the public payload fields.
4. Update `docs/unified-agentic-tool-runtime-contract.md` with the successful
   `visit` source receipt behavior and the explicit non-admission cases.
5. Run focused tests, changed-line coverage, scoped performance, and PR gates
   before opening the PR.

## Success Criteria

- Successful fixture-backed `visit` observations include one generic
  `tool_observation` receipt and one redacted `retrieved_document` source
  receipt.
- Successful workspace-local `visit` observations preserve
  `workspace_path_receipt` and include the same `retrieved_document` source
  receipt.
- Missing pages, workspace refusals, and unavailable workspace files do not emit
  admitted retrieved-document source receipts.
- Receipt fields expose source type, source id, source field, inclusion,
  policy, and owner-scope evidence without raw page or file text.
