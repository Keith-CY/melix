# Issue 1761 Owner Scope Boundary Plan

## Goal

Add the first owner-scope fail-closed boundary for fixture-backed retrieved
documents, images, pages, layouts, and crops in the deterministic agentic tool
runtime.

## Scope

This slice covers the Python worker deterministic agentic tool runtime:

- selected `text_search` retrieved document rows
- selected `image_search` retrieved image rows
- `visit` fixture pages
- `layout_parse` fixture layouts
- `image_crop` fixture crops
- the governing agentic tool runtime contract

This slice does not implement owner-scope checks for every future RAG store,
skill entrypoint, memory entrypoint, or background-job continuation. Those
remain follow-up work under #1761 once the shared receipt shape is established.

## Architecture

The end-state architecture is that every untrusted segment carries explicit
owner and privilege metadata before it can cross into prompt construction, tool
actions, or background continuation. This slice adds the first vertical
boundary at the existing deterministic agentic tool adapter layer.

Callers may provide an expected owner in fixture context as
`owner_scope.expected_owner_id`. Each retrieved segment can then declare
`owner_id`. When both values are present and differ, the adapter fails closed
before projecting the segment into an observation payload. The failed
observation uses a stable receipt shape:

- `reason = owner_scope_mismatch`
- `source_type`
- `source_id`
- `expected_owner_id`
- `actual_owner_id`
- `owner_scope_checked = true`
- `privilege`
- `corrective_action`

When no expected owner is configured, successful deterministic fixture behavior
remains unchanged. This keeps existing test fixtures and training-data replay
compatible while making owner-scoped runs opt in to explicit checks.

## Performance Probes And Metrics

The owner check is a small metadata comparison for retrieved records that the
adapters already inspect. There is no expected registered PR-scoped performance
probe for this change, but the PR must still include a scoped performance
report showing `Status: ok`, regressions `0`, and verification failures `0`.

Verification will include:

- focused pytest for the new owner-scope rejection paths
- full `services/mlx-worker-python/tests/test_agentic_tools.py`
- changed-line coverage for modified Python files with a target of at least
  95 percent
- local PR-scoped performance report with `Status: ok`

## Implementation Steps

1. Add failing tests in `services/mlx-worker-python/tests/test_agentic_tools.py`
   for cross-owner `text_search`, `image_search`, `visit`, `layout_parse`, and
   `image_crop` fixture payloads.
2. Implement owner-scope context parsing and a shared
   `owner_scope_mismatch` runtime error helper in
   `services/mlx-worker-python/worker/runtime/agentic_tools.py`.
3. Apply the helper before retrieved documents, images, pages, layouts, and
   crops are projected into observation payloads.
4. Update `docs/unified-agentic-tool-runtime-contract.md` with the owner-scope
   boundary and receipt fields.
5. Run focused tests, changed-line coverage, scoped performance, and PR gates
   before opening the PR.

## Success Criteria

- Cross-owner retrieved documents, images, pages, layouts, and crops produce
  failed observations, not successful prompt-visible payloads.
- Failed observations use a stable `owner_scope_mismatch` receipt shape with
  source and owner evidence.
- Existing successful deterministic tool behavior remains unchanged when no
  expected owner is configured or when the owner matches.
- Contract docs identify this as the first deterministic adapter owner-scope
  boundary under #1761, with broader RAG, skill, memory, and background-job
  entrypoints left for later slices.
