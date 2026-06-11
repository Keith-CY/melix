# Issue 1761 Workflow Continuation Receipt Admission Plan

## Goal

Add a workflow-facing prompt-boundary admission helper for already-redacted
workflow continuation results, so later workflow runner and agent surfaces can
reuse the same untrusted-context receipt path as background continuations.

## Scope

This slice covers:

- `worker.runtime.background_continuation.admit_workflow_continuation_result`;
- redacted workflow run/node identifiers mapped to the existing
  `background_continuation` source type;
- default workflow-specific receipt metadata;
- optional entrypoint-local receipt metadata inherited from
  `admit_background_continuation`;
- refusal receipts for malformed workflow run IDs, workflow node IDs, workflow
  result payloads, and owner-scope metadata.

This slice does not add a workflow runner, scheduler, MCP execution surface,
local-job side effects, prompt assembly integration, or owner-aware workflow
store lookup. Future workflow callers must redact result payloads and perform
any owner checks before calling this helper.

## Best End-State Architecture

Workflow continuation outputs should enter user-role prompt context through a
single admission surface before downstream prompt assembly can include them.
The admission helper should preserve the existing `background_continuation`
receipt schema because workflow continuation results have the same trust model:
they are local runtime output that can contain instructions and must remain
data-only prompt evidence.

Concrete workflow surfaces should provide stable redacted result identifiers
without copying raw workflow payloads, logs, command text, prompt text, or tool
arguments into receipt metadata.

## Performance Probes And Metrics

The helper performs a constant amount of string validation and constructs one
prompt-context receipt per admitted or refused workflow result. It adds no
filesystem access, network access, process polling, scheduler work, or model
inference.

Verification must include:

- focused Python tests for `test_background_continuation.py`;
- changed-line coverage for touched Python files with at least 95 percent
  coverage;
- full local pre-commit gate on this host;
- PR-scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`.

## Implementation Steps

1. Add focused tests for admitted workflow results with default metadata.
2. Add focused tests for workflow entrypoint-local receipt metadata.
3. Add focused tests for malformed workflow run IDs, workflow node IDs,
   workflow result payloads, and owner-scope metadata.
4. Implement `admit_workflow_continuation_result` as a thin wrapper around
   `admit_background_continuation`.
5. Update the unified runtime contract to point workflow runner surfaces at the
   new helper.
6. Run focused tests, coverage, full local gate, and PR performance checks.

## Success Criteria

- Workflow continuation results can be admitted with stable redacted workflow
  receipt identifiers.
- Malformed workflow metadata fails closed before prompt admission.
- Receipts preserve `source_type = background_continuation` and never include
  raw workflow result text.
- Existing background-continuation behavior remains unchanged.
