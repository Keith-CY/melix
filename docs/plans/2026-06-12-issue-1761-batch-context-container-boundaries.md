# Issue 1761 Batch Context Container Boundaries

## Goal

Make Python worker batch prompt-context projection helpers fail closed when the
top-level entry container is malformed.

## Scope

This slice covers:

- `worker.runtime.retrieval_context.project_retrieval_contexts`;
- `worker.runtime.skill_memory_context.project_skill_memory_contexts`;
- focused tests for non-list/tuple batch containers;
- contract documentation for batch projection container validation.

This slice does not implement new retrieval, skill, memory, workflow, session,
or local-job entrypoints. It only hardens the shared prompt-context projection
helpers used by those entrypoints.

## Best End-State Architecture

Concrete entrypoints should hand ordered, already-redacted entry descriptors to
shared projection helpers. Those helpers should validate both the top-level
container and each contained entry, returning typed refusal receipts for every
malformed boundary instead of relying on Python iteration behavior or leaking
implementation exceptions.

The container-level refusal should produce no user prompt payload, no admitted
receipts, and one `included = false` refusal receipt. Valid list/tuple behavior,
per-entry refusal isolation, duplicate-field refusal behavior, and side-effect
free projection remain unchanged.

## Performance Probes And Metrics

The change adds one constant-time container type check before the existing
linear projection pass. It adds no filesystem access, store lookup, network
work, model inference, or scheduler behavior.

Verification must include:

- focused red/green pytest runs for the new retrieval and skill/memory tests;
- adjacent prompt-context tests;
- changed-line coverage for touched Python files at 95 percent or higher;
- scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`;
- full local pre-commit gate before PR if the host hook requires it.

## Implementation Steps

1. Add failing tests in `test_retrieval_context.py` and
   `test_skill_memory_context.py` proving non-list/tuple batch containers return
   typed refusal receipts and no prompt payload.
2. Add minimal container guards to both projection helpers.
3. Update `docs/unified-agentic-tool-runtime-contract.md` to require list/tuple
   batch containers and document the refusal receipt behavior.
4. Run focused tests, adjacent tests, changed-line coverage, scoped
   performance, and the required local gate.

## Success Criteria

- Passing a dict, string, or other malformed top-level batch container no
  longer iterates arbitrary values or raises unrelated Python exceptions.
- The projection result contains no user payload or admitted receipts for a
  malformed top-level container.
- The projection result contains one typed refusal receipt that identifies the
  invalid `entries` boundary.
- Existing valid, per-entry invalid, duplicate, and unknown-kind behavior
  remains unchanged.
