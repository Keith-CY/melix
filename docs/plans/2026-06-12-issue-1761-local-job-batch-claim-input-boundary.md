# Issue 1761 Local Job Batch Claim Input Boundary Plan

## Goal

Harden the durable local-job batch follow-up claim entrypoint so malformed
caller-provided claim input maps fail closed per candidate instead of raising an
unstructured Python exception before prompt-context admission.

## Scope

This slice covers:

- the `LocalJobContinuationStore.claim_scanned_followup_prompt_contexts`
  wrapper inputs for follow-up session IDs, redacted completion summaries, and
  owner-scope decisions;
- deterministic per-candidate receipts when those wrapper inputs are malformed;
- focused Python tests proving malformed wrappers do not claim or drop sibling
  ready records;
- unified runtime contract documentation for future local-job monitor callers.

This slice does not change local-job record schema, reconciliation semantics,
prompt-admission receipts, live-evidence behavior, session projection, process
launch, log reading, artifact reading, or owner-scope inference.

## Best End-State Architecture

The best end-state keeps the monitor batch bridge as a typed boundary between
external monitor state and durable local-job claims. Candidate discovery remains
store-owned, prompt-context admission remains background-continuation-owned, and
the batch bridge is responsible for refusing malformed claim-input wrappers
before it indexes or trusts them.

Malformed wrapper inputs should therefore produce local-job continuation
receipts, not crashes. The bridge should continue processing other ready
candidates whose wrappers are valid, and it should leave refused candidates
unclaimed so a monitor can retry with corrected inputs.

## Performance Probes And Metrics

The changed path adds constant-time type checks for three caller-provided
wrapper values after the existing scandir-based candidate scan. It does not add
filesystem scans, file reads, process polling, network calls, model inference,
or additional prompt assembly work.

Verification must include:

- focused Python tests for `test_local_job_continuation.py`;
- changed-scope coverage for touched Python files with at least 95 percent
  coverage;
- PR-scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`;
- the full local pre-commit gate before PR merge.

## Implementation Steps

1. Add failing tests proving non-mapping batch input wrappers emit
   `followup_claim_input_invalid` receipts without claiming the candidate.
2. Add a sibling-candidate test proving a malformed wrapper for one input source
   does not prevent another ready job with valid wrappers from being claimed.
3. Add a small wrapper validation helper used by
   `claim_scanned_followup_prompt_contexts` before candidate indexing.
4. Update the unified runtime contract with the wrapper fail-closed behavior.
5. Run focused tests, changed-scope coverage, scoped performance, full
   pre-commit gate, and PR evidence validation.

## Success Criteria

- Non-mapping follow-up session ID, completion summary, or owner-scope wrapper
  inputs return per-candidate `followup_claim_input_invalid` receipts instead
  of unstructured exceptions.
- Malformed wrapper inputs do not persist an `in_progress` claim.
- Valid sibling candidates can still be claimed in the same batch.
