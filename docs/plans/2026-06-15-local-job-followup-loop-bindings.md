# Local job follow-up scan loop bindings

This Python performance slice is limited to `LocalJobContinuationStore.scan_followup_candidates(...)` in `services/mlx-worker-python/worker/runtime/local_job_continuation.py`.

## Goal

Keep local job follow-up scan behavior unchanged while reducing per-record Python overhead in large continuation stores. The scan already uses one `os.scandir(...)` pass; this slice avoids rebuilding the empty live-evidence mapping and binds hot loop callables once before iterating over record ids.

## Probe coverage

The affected path is covered by the registered PR-scoped performance probe `local-job-followup-scan-scandir` in `infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`, `coverage_command`, and `probe_command` entries and measures scan elapsed time, scan syscall shape, receipt/candidate counts, and follow-up projection metrics.

## Verification plan

1. Run focused local job continuation tests plus registry/probe tests.
2. Run changed-scope coverage for the touched Python paths and probe script.
3. Run the registered `local-job-followup-scan-scandir` probe locally on Linux against `origin/main` and this branch.
4. Use the PR-scoped performance workflow as the merge gate.

## Linux validation boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime behavior changes are included.
