# Local Job Follow-up Live Evidence None Fast Path

## Scope

This Python performance slice is limited to
`worker.runtime.local_job_continuation.LocalJobContinuationStore.scan_followup_candidates(...)`.
The scan path commonly runs without a `live_evidence_by_job_id` mapping while it
walks large local-job continuation stores.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`local-job-followup-scan-scandir` in `infra/perf/pr_scoped_probes.json`. The
probe includes focused `test_command`, `coverage_command`, and `probe_command`
entries and reports scan/projection metrics for the follow-up candidate scan.

## Change

When no live-evidence mapping is provided, the scan now passes `None` directly to
`reconcile_record(...)` instead of installing and calling a per-record fallback
lookup helper. Behavior remains unchanged because `reconcile_record(...)` already
uses `None` as its default live-evidence value; the change only removes one
Python function call per discovered record in the no-live-evidence hot path.

## Verification

Run the registered local-job follow-up test command, changed-scope coverage, and
registered probe locally on Linux. The expected signal is lower
`elapsed_ms_mean` for `local-job-followup-scan-scandir` while candidate,
receipt, projection, and scandir counts remain unchanged.

CI remains the merge gate for the PR-scoped performance workflow report.
