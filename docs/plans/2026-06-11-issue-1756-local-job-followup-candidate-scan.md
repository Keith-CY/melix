# Issue 1756 Local Job Follow-Up Candidate Scan Plan

## Goal

Add a side-effect-free store scan that lets a future local-job monitor discover
which durable local-job records are ready for exactly one follow-up, while still
reconciling stale persisted state against live evidence before returning
candidates.

## Scope

This slice covers:

- a store-level scan result that contains follow-up candidates and scan
  receipts;
- deterministic one-level scanning of local-job continuation record files;
- per-record reconciliation before candidate classification, so stale
  `completed` records can self-heal to `running` and missing completion evidence
  can block before a monitor attempts a follow-up claim;
- candidate receipts for evidence-backed completed records whose follow-up has
  not yet been claimed;
- skip/block receipts for already-claimed follow-ups and non-ready records;
- focused Python worker tests for ready, already-claimed, stale, missing
  evidence, live-evidence, running, and missing-root scan cases;
- contract documentation for future side-effecting monitor wiring.

This slice does not start local processes, poll process tables, tail logs, claim
follow-ups, inject prompt context, or resume sessions. Future monitors must
still call `claim_followup_prompt_context` before projecting any completed job
summary into prompt context.

## Best End-State Architecture

The local-job monitor should not decide readiness from stale JSON state alone.
It should ask the worker-owned store to reconcile every persisted record first,
then consume only records that are completed, have explicit completion evidence,
and have no existing follow-up claim. The scan therefore acts as the monitor's
read model, not as a side-effecting runner or session writer.

## Performance Probes And Metrics

The changed path performs a bounded one-level scan of `*.json` record files,
loads each record once, reconciles it with at most one caller-provided
`LocalJobLiveEvidence` value, and writes only records whose reconciliation
changes persisted state. It does not scan logs, enumerate process tables, start
subprocesses, or call model inference.

Success metrics:

- scan cost is O(record count) and O(1) per record beyond JSON load/optional
  reconciliation write;
- lock, temporary, and unrelated files are ignored by suffix;
- changed-line Python coverage for touched runtime and tests is at least
  95 percent;
- local and hosted PR-scoped performance reports are `Status: ok` with zero
  direct/gated regressions and zero verification failures.

## Implementation Steps

1. Add failing focused tests for store-level follow-up candidate scanning across
   ready, already-claimed, stale, missing-evidence, running, live-evidence, and
   missing-root records.
2. Add a frozen scan result type and `LocalJobContinuationStore.scan_followup_candidates`.
3. Reuse existing reconciliation and receipt helpers instead of introducing a
   separate local-job status vocabulary.
4. Document the scanner contract in the unified agentic runtime contract.
5. Run focused tests, changed-line coverage, diff checks, scoped performance,
   and the relevant full gates before PR merge.

## Success Criteria

- A future monitor can discover ready follow-up records without claiming them.
- Every scanned record is reconciled before candidate classification.
- Stale done records revive to running, missing-evidence completions block, and
  live completion evidence is persisted before a record appears as ready.
- Already-claimed records are never returned as candidates.
- The scanner remains a small runtime primitive with no runner, prompt, or
  session side effects.
