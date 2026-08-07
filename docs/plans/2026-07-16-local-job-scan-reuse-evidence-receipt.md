# Local Job Scan Reuse Evidence Receipt Slice

## Scope

Optimize the Python local-job follow-up scan hot path in
`worker.runtime.local_job_continuation` without changing continuation record,
reconciliation, candidate, or receipt semantics.

## Performance Probe

The slice is covered by the registered PR-scoped probe
`local-job-followup-scan-scandir` in `infra/perf/pr_scoped_probes.json`.
The probe runs focused local-job continuation tests, changed-scope coverage, and
`scripts/local_job_followup_scan_probe.py`. This slice extends that probe with a
candidate receipt microprobe comparing the previous candidate receipt path, which
recomputed completion evidence from the reconciled record, against the optimized
path that reuses the boolean already emitted by reconciliation.

## Implementation Plan

- Preserve scan ordering, reconciliation output, and follow-up candidate receipt
  fields.
- Reuse `reconciliation.receipt["completion_evidence_available"]` when it is a
  boolean while building scan-level candidate receipts.
- Keep `_followup_candidate_scan_receipt()` backwards compatible by falling back
  to `_has_completion_evidence(record)` when no trusted evidence boolean is
  supplied.
- Add a focused regression test proving the scan path does not perform a second
  completion-evidence check after reconciliation has already produced the same
  evidence availability boolean.

## Linux Validation Boundary

This is a Python-only slice and is locally measurable on Linux. Swift runtime
validation is not involved.
