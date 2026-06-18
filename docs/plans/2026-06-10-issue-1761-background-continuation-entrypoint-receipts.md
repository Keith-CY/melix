# Issue 1761 Background Continuation Entrypoint Receipt Metadata Plan

## Goal

Continue the background-continuation boundary work by allowing concrete
entrypoints to attach local receipt metadata when admitting already-redacted
background job evidence into user-role prompt context.

## Scope

This slice covers:

- optional `segment_id`, `source_field`, `reason`, and `corrective_action`
  parameters on `worker.runtime.background_continuation.admit_background_continuation`;
- refusal receipts for malformed entrypoint-local metadata before prompt
  admission;
- focused Python tests for admitted metadata, malformed metadata, and the
  existing default behavior;
- contract documentation that future local-job, workflow, and session
  continuation entrypoints must use this metadata surface instead of inventing
  ad hoc receipt fields.

This slice does not implement a durable job runner, live process monitor,
workflow scheduler, or session resume loop. It only standardizes the receipt
metadata surface those later entrypoints will call.

## Best End-State Architecture

Background job follow-up data should flow through a single prompt-boundary
helper before it is projected into a prompt payload. Store-specific or
entrypoint-specific details belong in redacted receipt metadata, not in raw
prompt text or custom side-channel receipt shapes.

The helper should keep a stable default for callers that only know a job ID, but
also allow concrete entrypoints to identify the exact result slot or workflow
field they are admitting. Invalid metadata must fail closed with the same
`melix.untrusted_context_receipt.v1` shape as malformed job IDs, summaries, and
owner-scope metadata.

## Performance Probes And Metrics

The changed path normalizes at most four short metadata strings and emits one
receipt per admitted or refused continuation payload. Runtime cost remains
constant per continuation payload and does not add filesystem polling, log
scanning, scheduler work, or model inference.

Verification must include:

- focused Python tests for `test_background_continuation.py`;
- changed-line coverage for touched Python files with at least 95 percent
  coverage;
- full local pre-commit gate on this host;
- PR-scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`.

## Implementation Steps

1. Add focused tests proving `admit_background_continuation` accepts
   entrypoint-local `segment_id`, `source_field`, `reason`, and
   `corrective_action` while omitting raw job output from receipts.
2. Add focused tests proving malformed entrypoint metadata fails closed with
   `included = false` refusal receipts and no user payload.
3. Implement metadata normalization in `worker.runtime.background_continuation`
   while preserving existing defaults:
   - `segment_id = <job_id>:background-continuation`;
   - `source_field = background_job`;
   - default reason and corrective action supplied by the shared source
     evidence helper.
4. Update the unified runtime contract so later local-job and workflow
   continuation entrypoints use this helper surface.
5. Run focused tests, changed-line coverage, the full local gate, and the PR
   performance workflow before merge.

## Success Criteria

- Concrete background-continuation entrypoints can record redacted local receipt
  metadata without changing prompt payload semantics.
- Malformed metadata is refused before prompt admission with
  `invalid_background_continuation_field`.
- Existing callers keep the same default receipt shape.
- The implementation remains a prompt-boundary primitive and does not introduce
  durable job or workflow behavior.
