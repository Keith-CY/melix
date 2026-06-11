# Issue 1761 Local Job Follow-Up Prompt Receipt Plan

## Goal

Connect the durable local-job follow-up claim primitive to the existing
background-continuation prompt-context receipt boundary, so a successful claim
records redacted prompt-boundary evidence before any future monitor projects a
follow-up into user-role prompt context.

## Scope

This slice covers:

- adding redacted `background_continuation` prompt-context receipt evidence to
  successful `LocalJobContinuationStore.claim_followup` receipts;
- using `worker.runtime.background_continuation.admit_background_continuation`
  for the receipt shape instead of constructing an ad hoc local-job boundary;
- recording the boundary without copying command vectors, working directories,
  log paths, session IDs, success marker paths, artifact paths, or raw job log
  output into prompt-context receipt JSON;
- focused Python tests for successful claim receipt evidence and unchanged
  duplicate or non-ready claim behavior;
- contract documentation for future monitors that consume the claim result.

This slice does not start shell jobs, tail logs, inject prompt follow-ups,
resume sessions, add owner-aware job lookup, or change the durable job record
schema. It only makes the existing follow-up claim receipt carry the prompt
boundary evidence a later side-effecting monitor must preserve.

## Best End-State Architecture

The local-job monitor should claim a completed evidence-backed job exactly once,
then project a redacted completion summary through the shared
background-continuation prompt-context admission surface. The claim receipt is
the durable handoff between the state transition and later prompt projection,
so it should expose the untrusted-context receipt for the admitted
background-continuation segment while keeping private local execution details
out of the receipt.

The local-job record still owns local execution truth. Prompt-context receipts
only describe trust classification and source metadata; they do not make local
job output trusted, do not prove owner scope, and do not replace completion
evidence checks.

## Performance Probes And Metrics

The changed path emits one receipt for the successful claim branch after the
existing bounded record read and guarded write decision. It does not add log
scanning, filesystem enumeration, process polling, subprocess launch, model
inference, or network calls.

Verification must include:

- focused Python tests for `test_local_job_continuation.py` and adjacent
  `test_background_continuation.py`;
- changed-line coverage for touched Python files with at least 95 percent
  coverage;
- full local pre-commit gate on this host;
- PR-scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`.

## Implementation Steps

1. Add failing tests proving a successful local-job follow-up claim includes one
   redacted prompt-context receipt with `source_type = background_continuation`
   and `owner_scope_checked = false`.
2. Add test assertions that the receipt JSON does not include local command,
   cwd, log path, session ID, success marker path, or artifact path data.
3. Reuse `admit_background_continuation` from
   `worker.runtime.local_job_continuation` to build the receipt and attach only
   receipt metadata to the local-job receipt.
4. Update the unified runtime contract to describe the local-job claim receipt
   handoff for future monitors.
5. Run focused tests, changed-line coverage, full local pre-commit, and the PR
   performance workflow before merge.

## Success Criteria

- A successful `followup_claimed` receipt carries prompt-boundary evidence for
  exactly one background-continuation segment.
- Duplicate, blocked, and not-ready claims do not enqueue or emit a new admitted
  prompt-context segment.
- Prompt-context receipt JSON remains redacted from command, path, session,
  artifact, and log payload details.
- The implementation remains a prompt-boundary receipt slice and does not add
  runner, monitor, owner-scope, or prompt-injection side effects.
