# Issue 1756 Local Job Session Follow-Up Batch Projection Plan

## Goal

Add a side-effect-free batch projection helper for local-job session follow-ups
so future monitor loops can turn claimed follow-up prompt contexts into
user-role session message payloads without manually stitching receipts together.

## Scope

This slice covers:

- a Python worker projection envelope for a batch of local-job follow-up claims;
- a helper that delegates to
  `LocalJobContinuationStore.claim_scanned_followup_prompt_contexts`;
- per-claim `LocalJobSessionFollowupProjection` values that copy claim receipts,
  prompt user payloads, untrusted-context receipts, and user-role follow-up
  messages;
- preservation of existing scan, claim, admission-refusal, and revision-race
  receipts for non-projected candidates;
- focused tests proving the helper emits only admitted user-role data and does
  not leak command vectors, local paths, session IDs, artifact paths, or raw
  completion summaries into receipt JSON.

This slice does not launch local jobs, tail logs, read artifacts, mutate a
session store, enqueue UI work, infer owner scope, resume workflows, or add a
long-lived monitor loop. Callers still provide redacted completion summaries,
follow-up session IDs, owner-scope decisions, and optional live evidence.

## Best End-State Architecture

The durable store remains the only owner of record reconciliation and guarded
claim transitions. Prompt-context admission remains the only owner of the
background-continuation untrusted-context receipt. The new batch projection
helper owns only the monitor-facing shape: a claim batch plus copied
per-claim session message projections that future monitor/UI/session code can
consume without reinterpreting claim internals.

Keeping this bridge side-effect-free makes the eventual monitor loop smaller
and easier to verify. A monitor can call one helper, inspect typed receipts for
all candidates, and enqueue only `followup_message` values from successful
projections.

## Performance Probes And Metrics

The changed path adds constant-size dictionary/list copying per successful
claim after the existing store scan, prompt admission, and guarded save. It
does not add filesystem enumeration beyond the existing `os.scandir` scan, does
not tail logs, and does not execute subprocesses.

Verification must include:

- focused Python tests for `test_local_job_continuation.py`;
- changed-scope coverage for touched Python files with at least 95 percent
  coverage;
- PR-scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`;
- full local gate before merge when feasible.

## Implementation Steps

1. Add a failing test for a batch with two ready records and one blocked record.
   The test must assert that the new helper returns two projections ordered like
   the claimed records, each projection contains a user-role `followup_message`,
   and the batch receipts still include the blocked candidate receipt.
2. Add a failing test for prompt-admission refusal. The helper must return no
   projections, preserve the existing `followup_prompt_context_refused` receipt,
   preserve refusal receipts, and leave the store record unclaimed.
3. Implement `LocalJobSessionFollowupProjectionBatch` and
   `project_local_job_session_followups(...)` in
   `worker.runtime.local_job_continuation`.
4. Keep the helper on the `worker.runtime.local_job_continuation` module without
   widening the legacy star-import surface.
5. Update `docs/unified-agentic-tool-runtime-contract.md` to require future
   monitor/session callers that process multiple candidates to use the batch
   helper rather than manually projecting claim batches.
6. Run focused tests, changed-scope coverage, scoped performance, and PR
   evidence validation before opening the PR.

## Success Criteria

- Successful batch projection emits one user-role follow-up message per
  admitted claim and no messages for blocked, duplicate, not-ready, missing, or
  refused candidates.
- The projection returns copied claim receipts, prompt user payloads, and
  untrusted-context receipts so downstream callers cannot mutate the underlying
  claim admission objects.
- Batch-level receipts and refusal receipts are preserved exactly for monitor
  auditing.
- Receipt JSON does not copy command vectors, working directories, log paths,
  session IDs, success marker paths, artifact paths, raw logs, raw prompt text,
  or raw completion summary text.
