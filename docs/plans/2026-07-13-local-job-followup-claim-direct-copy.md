# Local Job Follow-up Claim Direct Copy Slice

## Scope

Optimize the Python local-job follow-up claim hot path in
`worker.runtime.local_job_continuation` without changing continuation record or
receipt semantics.

## Performance Probe

The slice is covered by the registered PR-scoped probe
`local-job-followup-scan-scandir` in `infra/perf/pr_scoped_probes.json`.
The probe runs focused local-job continuation tests, changed-scope coverage, and
`scripts/local_job_followup_scan_probe.py`, including the projection benchmark
that exercises repeated follow-up claims and a direct claim-copy microprobe that
compares the previous `dataclasses.replace()` transition against the narrow
constructor copy.

## Implementation Plan

- Preserve record validation, schema, and receipt output.
- Replace the `dataclasses.replace()` call used only for the successful
  follow-up claim transition with a narrow constructor copy that updates
  `followup_status` and `followup_session_id`.
- Rebuild follow-up reconciliation wrappers directly after persistence so the
  projection batch path also avoids `dataclasses.replace()` at the claim seam.
- Add a regression test proving the successful claim path does not depend on
  `dataclasses.replace()`.

## Linux Validation Boundary

This is a Python-only slice and is locally measurable on Linux. Swift runtime
validation is not involved.
