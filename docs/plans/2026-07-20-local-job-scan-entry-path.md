# Local Job Follow-up Scan Entry Path Fast Path

## Context

The registered PR-scoped probe `local-job-followup-scan-scandir` covers
`worker.runtime.local_job_continuation` follow-up scanning, claim projection, and
JSON-like payload copy helpers used by local-job follow-up receipts.

`LocalJobContinuationStore.scan_followup_candidates()` already uses a single
`os.scandir()` pass to collect `.json` record names, then calls
`reconcile_record(job_id)` for each candidate. That second step rebuilds the
same root-relative record path for every scanned file via `_record_path_text()`.
For large follow-up stores, the scanned directory entry already provides the
stable path to open, so this slice avoids the redundant path reconstruction for
scan-originated records while keeping the public `reconcile_record()` API
unchanged.

## Scope

- Limit code changes to local-job follow-up scan loading in
  `services/mlx-worker-python/worker/runtime/local_job_continuation.py`.
- Preserve scan ordering, symlink filtering, unreadable-record receipts, missing
  root handling, and normal `reconcile_record()` behavior for non-scan callers.
- Update focused local-job continuation tests for the scanned-entry-path fast
  path.

## Measurement

Registered probe: `local-job-followup-scan-scandir`

Required local Linux commands:

- Focused registry test command for `local-job-followup-scan-scandir`.
- Changed-scope coverage command for the same registry entry.
- Registered probe command from `infra/perf/pr_scoped_probes.json`.

Success is accepted only if behavior tests pass, changed-scope coverage remains
at or above 95%, and the local registered probe remains directionally
non-regressive for scan/copy metrics. GitHub Actions PR-scoped performance is
the merge gate after push.

## Linux Boundary

This is a Python worker path and can be validated locally on Linux. CI remains
the source of truth for the registered PR-scoped performance report after the PR
is opened.
