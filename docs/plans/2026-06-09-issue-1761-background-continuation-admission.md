# Issue 1761 Background Continuation Admission Plan

## Goal

Add a small Python worker primitive that validates background-job follow-up
context before it can be projected into user-role prompt payloads, and records
admitted or refused `background_continuation` untrusted-context receipts through
the shared prompt-context admission helper.

## Scope

This slice covers:

- `worker.runtime.background_continuation` as a reusable admission/refusal
  boundary for future durable background job follow-up work.
- Focused Python tests for admitted background continuation payloads, refusal
  receipts for malformed fields, and reuse of `admit_prompt_context_segments`.
- `docs/unified-agentic-tool-runtime-contract.md` documentation for the
  background continuation primitive.

This slice does not implement a durable job runner, monitor, restart recovery,
or session resume loop. Those remain under #1756 and later #1761 slices. It
also does not copy command text, logs, or session contents into receipts.

## Best End-State Architecture

Background job follow-up is untrusted local context. The future durable
continuation monitor should call a narrow admission helper with already redacted
job evidence, receive a user-role prompt payload, and attach receipt evidence
that records the data-only boundary without raw job output.

The helper belongs in the Python worker runtime beside `prompt_context` and
`tool_observation`: it is a prompt-boundary primitive, not a scheduler or job
store. It should delegate receipt creation to `admit_prompt_context_segments`
and `refused_prompt_context_receipt` so background continuation evidence uses
the same schema as retrieved docs, skills, memories, chat projections, and tool
observations.

## Performance Probes And Metrics

The changed path validates a small metadata dictionary and emits one receipt
per continuation payload. Runtime cost is constant per finished background job
follow-up and does not add model inference, filesystem polling, log scanning,
or scheduler work.

Verification must include:

- focused red/green tests for `test_background_continuation.py`;
- changed-line coverage for the touched Python files with at least 95 percent
  coverage;
- full local pre-commit gate before commit on this host;
- PR-scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`.

## Implementation Steps

1. Add failing tests for `admit_background_continuation`:
   - accepted payload returns `PromptContextAdmission.user_payload` with
     `background_job` and a receipt whose `source_type` is
     `background_continuation`;
   - receipts omit raw log tail text;
   - monkeypatching `admit_prompt_context_segments` proves the helper uses the
     shared prompt-context primitive.
2. Add failing tests for malformed payload fields:
   - non-string `job_id`, non-dict `job_summary`, and non-boolean
     `owner_scope_checked` are refused before admission;
   - each refusal carries an `included=false` receipt with reason
     `invalid_background_continuation_field`.
3. Implement `worker.runtime.background_continuation` with:
   - `BackgroundContinuationAdmissionError`;
   - `admit_background_continuation(job_id, job_summary, owner_scope_checked)`;
   - deterministic `segment_id = <job_id>:background-continuation`;
   - `source_field = background_job`;
   - source ID equal to the redacted job ID.
4. Update the unified agentic tool runtime contract to specify this primitive
   as the required future #1756/#1761 admission boundary for background job
   follow-up context.
5. Run focused tests, changed-line coverage, full local gate, and PR-scoped
   performance before opening the PR.

## Success Criteria

- Background continuation follow-up context can be admitted through a reusable
  primitive before prompt projection.
- Refused malformed continuation fields produce machine-readable refusal
  receipts and no user payload.
- Receipt evidence uses `melix.untrusted_context_receipt.v1`, records
  `source_type = background_continuation`, and omits raw log content.
- The implementation does not create a durable job runner or change existing
  chat/session behavior.
