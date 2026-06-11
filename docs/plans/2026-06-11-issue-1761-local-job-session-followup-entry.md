# Issue 1761 Local Job Session Follow-Up Entry Plan

## Goal

Add a side-effect-free session follow-up entrypoint for completed local jobs so
future UI and session callers can claim exactly one follow-up and receive the
already-admitted user payload plus redacted untrusted-context receipts.

## Scope

This slice covers:

- a Python worker helper that wraps
  `LocalJobContinuationStore.claim_followup_prompt_context` for session follow-up
  projection;
- an explicit return object carrying the persisted claim receipt, prompt
  user-payload, untrusted-context receipts, and a session-message projection;
- blocker behavior for missing, not-ready, duplicate, and malformed prompt
  context cases without creating a trusted prompt segment;
- focused Python tests proving the projection stays user-role data and keeps
  prompt receipts redacted;
- unified runtime contract documentation for future UI/session monitor callers.

This slice does not launch local jobs, tail logs, start UI flows, send HTTP
requests, resume workflows, infer owner scope, or read artifact contents. The
caller must provide an already-redacted completion summary and the owner-scope
decision for that summary.

## Best End-State Architecture

The best end-state has three explicit layers. The durable store owns local-job
state and the single-claim transition. The prompt-boundary admission helper owns
classification of the redacted completion summary as untrusted user data. The
session follow-up entrypoint owns only the projection shape that a future UI or
session queue can pass forward without reinterpreting receipts or copying hidden
local execution details.

Keeping this projection side-effect-free makes it safe for local-job monitors
and UI/session surfaces to adopt incrementally. It also keeps failure modes
typed: store blockers return no prompt payload, while malformed prompt context
raises the existing admission error before any claim is persisted.

## Performance Probes And Metrics

The changed path adds constant-size dictionary assembly after the existing store
load, reconciliation, prompt admission, and guarded save. It does not add
filesystem enumeration, log reading, subprocess launch, network access, model
inference, or long-running polling.

Verification must include:

- focused Python tests for `test_local_job_continuation.py`;
- adjacent prompt-boundary tests for `test_background_continuation.py` and
  `test_prompt_context.py`;
- changed-scope coverage for touched Python files with at least 95 percent
  coverage;
- PR-scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`;
- full local gate when feasible before merge.

## Implementation Steps

1. Add failing tests for a successful completed-job session projection. The test
   must assert:
   - `followup_message["role"] == "user"`;
   - `followup_message["content"]` equals the admitted prompt user payload;
   - `followup_message["untrusted_context_receipts"]` equals the admission
     receipts;
   - the projection does not leak command vectors, local paths, session IDs, or
     raw completion summary text into receipt JSON.
2. Add failing tests for store blockers and missing records. Missing records
   return `None`; store blockers return an empty projection with the blocker
   receipt and no user payload.
3. Implement a `LocalJobSessionFollowupProjection` dataclass and
   `project_local_job_session_followup(...)` helper in
   `worker.runtime.local_job_continuation`.
4. Keep `LocalJobContinuationAdmissionError` propagation unchanged for malformed
   summaries or owner-scope metadata so no `in_progress` claim is persisted.
5. Update `docs/unified-agentic-tool-runtime-contract.md` to require future
   local-job monitor, UI, and session follow-up callers to use the projection
   entrypoint instead of manually stitching claim receipts into prompts.
6. Run focused tests, changed-scope coverage, scoped performance, and the PR
   evidence validator before opening the PR.

## Success Criteria

- Session follow-up projection produces exactly one user-role prompt message for
  a successful completed-job claim.
- The message content comes from `PromptContextAdmission.user_payload`, not from
  raw local-job record fields.
- Redacted untrusted-context receipts are attached to the projection and do not
  copy private command, path, session, artifact, log, or summary text.
- Missing, duplicate, blocked, and not-ready records do not create a prompt
  message payload.
