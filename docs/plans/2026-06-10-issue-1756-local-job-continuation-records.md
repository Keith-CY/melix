# Issue 1756 Local Job Continuation Records Plan

## Goal

Add the first durable local-job continuation primitive for long-running Melix
workflows: a persistent record schema, an optimistic and locked JSON store, and
side-effect-free reconciliation receipts that reject stale completion state
unless explicit completion evidence is present.

## Scope

This slice covers:

- `worker.runtime.local_job_continuation` with a versioned local-job
  continuation record;
- JSON persistence for one record per job ID, with atomic replacement,
  cross-platform-safe record filenames, per-record write locks, identity-checked
  stale lock recovery, and revision guards for concurrent writer detection;
- live-session reconciliation for stale `completed` records without success or
  artifact evidence;
- a store-backed reconciliation entrypoint that loads the latest persisted
  record, applies live evidence, and writes revived or evidence-enriched state
  back with the record revision guard;
- a store-backed follow-up claim primitive that marks an evidence-backed
  completed job as `in_progress` exactly once before a later monitor projects
  prompt follow-up data;
- typed receipts for `live_session_reused`, `stale_done_revived`,
  `completion_evidence_accepted`, `missing_completion_evidence`,
  `followup_claimed`, `followup_already_claimed`, `followup_not_ready`, and
  store write refusal cases;
- focused Python tests for record round-trip, stale-state self-healing,
  duplicate-launch refusal through live-session reuse, completion evidence
  gating, and write guards;
- contract documentation for later runner and monitor wiring.

This slice does not start shell commands, poll processes, tail logs, inject chat
follow-ups, or resume a workflow session. Future runner and monitor slices will
use this primitive before adding side effects. The follow-up claim primitive is
the monitor-side state transition that future side-effecting monitors must
perform before prompt projection.

## Best End-State Architecture

Durable background local jobs should have one persisted source of local truth
that is reconciled against live process or session evidence before Melix starts
duplicates or declares completion. Persisted state is advisory: a record marked
`completed` is not final until the monitor can also point to a success marker or
artifact path. If a live session with matching progress is still active, the
record should self-heal back to `running` and report why.

The Python worker owns the local execution evidence surface for this first
slice. The Swift control plane and chat/session monitor should later treat the
record and receipts as worker-owned evidence rather than inventing separate job
status semantics.

## Performance Probes And Metrics

The changed path reads or writes one bounded JSON record per job ID and compares
small metadata fields. It does not scan job logs, enumerate process tables,
start subprocesses, or invoke model inference.

Success metrics:

- reconciliation remains O(1) in record size and live-evidence size;
- atomic store writes touch one temporary JSON file and one lock file per write,
  with one liveness probe and one short-lived recovery guard when a stale lock
  candidate exists;
- store-backed reconciliation performs one bounded record read and, only when
  state changes, one guarded atomic record write;
- follow-up claiming performs one bounded record read and, only when a
  completed evidence-backed record is claimable or blocked by missing evidence,
  one guarded atomic record write;
- changed-line Python coverage for the touched runtime module and tests is at
  least 95 percent;
- local and hosted PR-scoped performance reports are `Status: ok` with zero
  direct/gated regressions and zero verification failures.

## Implementation Steps

1. Add focused tests for:
   - versioned record serialization and JSON store round-trip;
   - stale `completed` state without evidence self-healing to `running` when
     live progress is observed;
   - duplicate launch refusal through a `live_session_reused` receipt when the
     same session is already active;
   - completed records being accepted only after success marker or artifact path
     evidence is present;
   - store lock, identity-checked stale-lock recovery, unsafe job ID rejection,
     and revision mismatch write guards.
2. Implement `LocalJobContinuationRecord`, `LocalJobLiveEvidence`,
   `LocalJobContinuationStore`, and `reconcile_local_job_continuation`.
3. Add store-backed reconciliation so future monitors can self-heal stale
   persisted state in place without bypassing revision guards.
4. Add store-backed follow-up claiming so a future monitor can reserve exactly
   one prompt follow-up for an evidence-backed completed job while preserving
   duplicate-claim and missing-evidence receipts.
5. Record the contract in the unified agentic runtime document beside the
   existing background-continuation prompt-boundary primitive.
6. Run focused tests, changed-line coverage, full local pre-commit, and the PR
   performance gate before merge.

## Success Criteria

- A future runner can persist command, cwd, log path, exit status, timeout,
  session ID, follow-up status, follow-up session ID, and completion evidence in
  a stable record shape.
- A stale `completed` record without completion evidence cannot be accepted as
  final.
- A live matching session is reused instead of duplicated, with a typed receipt.
- Store-backed reconciliation persists revived running state and live completion
  evidence with optimistic revision protection.
- Store-backed follow-up claiming marks an evidence-backed completed record
  `in_progress` exactly once, persists live completion evidence before claiming
  when needed, and rejects duplicate or premature claims with typed receipts.
- Concurrent record writes are rejected before silent overwrite, while stale
  lock files left by dead writer processes may be recovered without human
  cleanup after the stale file is guarded, renamed, and revalidated.
- The PR stays focused on the state/reconciliation primitive and leaves runner,
  monitor, and chat follow-up side effects to later slices.
