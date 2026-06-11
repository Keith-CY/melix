# Issue 1761 Local Job Follow-Up Prompt Admission Plan

## Goal

Wire the durable local-job continuation store to the shared
background-continuation prompt-boundary helper so a claimed follow-up cannot
project local-job completion data into user-role prompt context without an
explicit untrusted-context receipt.

## Scope

This slice covers:

- a store-backed local-job follow-up claim entrypoint that admits an
  already-redacted completion summary through
  `worker.runtime.background_continuation.admit_background_continuation`;
- stable local-job receipt metadata for admitted prompt context;
- fail-closed behavior when completion summaries or owner-scope metadata are
  malformed;
- focused Python tests proving refused prompt context does not persist a
  follow-up claim;
- contract documentation for future monitor/session callers.

This slice does not start local jobs, monitor processes, tail logs, read
artifacts, infer owner scope, or enqueue session follow-up messages. Callers
must pass already-redacted summaries and perform owner checks before this
entrypoint can admit prompt context.

## Best End-State Architecture

Durable local-job continuation has two distinct boundaries:

1. the store boundary reconciles and claims exactly one eligible follow-up; and
2. the prompt boundary admits only redacted completion summaries as data-only
   user prompt context.

The best end-state keeps those boundaries explicit and prevents a claim from
being persisted when the prompt-boundary admission fails. That lets future
monitor loops retry safely after fixing malformed or missing redaction/owner
metadata, while preserving the existing optimistic revision guard for
concurrent claims.

## Performance Probes And Metrics

The changed path performs one existing store load, one existing reconciliation
claim, one constant-size prompt-context admission, and one existing guarded
store write only after admission succeeds. It does not add filesystem scanning,
log reading, process polling, network access, or model inference.

Verification must include:

- focused Python tests for `test_local_job_continuation.py`;
- focused background-continuation regression tests;
- changed-line coverage for touched Python files with at least 95 percent
  coverage;
- full local pre-commit gate on this host;
- PR-scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`.

## Implementation Steps

1. Add focused tests for a completed evidence-backed local job whose follow-up
   claim returns an admitted prompt-context payload and receipt.
2. Add focused tests proving malformed completion summaries and non-boolean
   owner-scope metadata raise background-continuation refusal receipts before
   the follow-up claim is persisted.
3. Add a `LocalJobContinuationFollowupClaim` result and
   `LocalJobContinuationStore.claim_followup_prompt_context` method that admits
   prompt context before writing a new `in_progress` follow-up claim.
4. Keep existing `claim_followup` behavior unchanged for callers that only need
   the store-level claim.
5. Update the unified runtime contract to require future local-job monitor and
   session follow-up callers to use the store-backed prompt-admission entrypoint
   before prompt projection.
6. Run focused tests, changed-line coverage, full local gate, and PR-scoped
   performance before merge.

## Success Criteria

- Evidence-backed local-job follow-up claims emit a redacted
  `background_continuation` untrusted-context receipt before prompt projection.
- Malformed local-job completion summaries or owner-scope metadata fail closed
  without mutating the stored follow-up claim.
- Existing reconciliation, duplicate-claim, and revision-guard behavior remains
  unchanged.
