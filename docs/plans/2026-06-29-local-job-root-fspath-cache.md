# Local Job Follow-up Scan Root Fspath Cache

## Slice

Optimize the registered `local-job-followup-scan-scandir` Python path by reusing the `LocalJobContinuationStore` constructor-cached filesystem path string when scanning follow-up records.

## Scope

- Production path: `services/mlx-worker-python/worker/runtime/local_job_continuation.py`
- Registered probe: `local-job-followup-scan-scandir`
- Tests/probe remain governed by the existing registry entry in `infra/perf/pr_scoped_probes.json`.

## Behavior Contract

The change is behavior-preserving: `scan_followup_candidates()` must still scan exactly one directory with `os.scandir`, ignore non-JSON entries and directory entries, preserve sorted job-id processing, tolerate a missing root, and avoid following record symlinks.

## Measurement Plan

Run the registered focused test command, changed-scope coverage command, and registered probe locally on Linux before opening the PR. The performance decision is based on the registered probe's `elapsed_ms_mean` while keeping `scandir_calls_mean == 1`, `path_glob_calls_mean == 0`, and candidate/receipt counts unchanged.

## Linux Boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime effect is claimed.
