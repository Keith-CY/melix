# Issue 1756 Local Job Follow-Up Scan Claim Plan

## Goal

Add a store-level bridge that lets a future local-job monitor scan durable
follow-up candidates and claim only prompt-admitted completions in one bounded
operation, while still keeping session resume and workflow mutation out of this
slice.

## Scope

This slice covers:

- a batch claim result type that separates claimed prompt contexts from scan,
  claim, store-conflict, and prompt-admission receipts;
- a `LocalJobContinuationStore.claim_scanned_followup_prompt_contexts`
  entrypoint that first calls `scan_followup_candidates`, then calls
  `claim_followup_prompt_context` for each ready candidate;
- caller-provided follow-up session IDs and already-redacted completion
  summaries keyed by job ID;
- prompt-admission refusal handling that records refusal receipts and does not
  persist a follow-up claim;
- per-candidate store-conflict isolation so one revision race cannot stop other
  ready local-job follow-ups;
- focused Python worker tests for successful multi-claim, missing claim inputs,
  admission refusal, and revision-race isolation;
- contract documentation for the future side-effecting monitor loop.

This slice does not start local processes, poll process tables, tail logs,
write to session stores, inject prompt context into an agent loop, or resume
workflow execution. Future monitor wiring must consume the returned prompt
contexts and perform session writes under the appropriate session concurrency
guard.

## Best End-State Architecture

The monitor should use the store as the single durable boundary for local-job
follow-up claims. Scanning remains the side-effect-free read model for
discovering ready records. Claiming a ready record must first prove that its
completion summary can be admitted as user-role prompt data; only then may the
record transition to `followup_status = in_progress`. The batch bridge keeps
that sequence explicit while avoiding monitor-side loops that could accidentally
claim a follow-up after prompt admission has failed.

## Performance Probes And Metrics

The changed path performs one bounded `scan_followup_candidates` pass plus one
bounded claim attempt per returned ready candidate. It does not enumerate
process tables, read log files, launch subprocesses, or call model inference.

Success metrics:

- scan cost remains O(record count);
- claim cost is O(ready candidate count);
- missing per-job claim inputs, admission refusals, and store revision races are
  reported per candidate and do not abort the batch;
- changed-line Python coverage for touched runtime and tests is at least
  95 percent;
- local and hosted PR-scoped performance reports are `Status: ok` with zero
  direct/gated regressions and zero verification failures.

## Implementation Steps

1. Add focused failing tests for batch scan-and-claim behavior.
2. Add a frozen result type for claimed follow-up prompt contexts and receipts.
3. Implement `claim_scanned_followup_prompt_contexts` by composing the existing
   scanner and `claim_followup_prompt_context`.
4. Document the monitor bridge in the unified runtime contract.
5. Run focused tests, changed-line coverage, diff checks, scoped performance,
   and the relevant full gates before PR merge.

## Success Criteria

- A future monitor can atomically discover ready local-job follow-ups and claim
  only those whose redacted completion summaries are prompt-admitted.
- Duplicate, not-ready, missing-summary, admission-refused, and store-conflict
  cases are visible in receipts without stopping unrelated candidates.
- A failed prompt-admission path leaves the durable follow-up status unchanged.
- The primitive remains a store-level bridge with no session, runner, process,
  or prompt-projection side effects.
