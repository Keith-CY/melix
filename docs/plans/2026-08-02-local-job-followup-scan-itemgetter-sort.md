# Local Job Follow-up Scan Itemgetter Sort Slice

## Scope

This Python-only performance slice is limited to `LocalJobContinuationStore.scan_followup_candidates()` in `services/mlx-worker-python/worker/runtime/local_job_continuation.py`.

The affected path is already covered by the registered PR-scoped probe `local-job-followup-scan-scandir` in `infra/perf/pr_scoped_probes.json`. That registry entry includes focused `test_command`, `coverage_command`, and `probe_command` coverage for the local job follow-up scan path.

## Optimization

The scan still performs a deterministic sort of discovered JSON records by `job_id` after a single `os.scandir()` pass. This slice replaces the per-comparison Python lambda key with `operator.itemgetter(0)` so the key extraction stays in the C-backed helper while preserving the same ordering and follow-up candidate behavior.

## Verification Plan

Run the registered focused tests, changed-scope coverage, and registered probe locally on Linux before pushing. GitHub Actions PR-scoped performance remains the merge gate after the PR is opened.

## Local Baseline

Baseline from `origin/main` (`f5c05870`) using the registered probe with `MELIX_LOCAL_JOB_SCAN_RECORDS=1200` and `MELIX_LOCAL_JOB_SCAN_SAMPLES=7`:

- `elapsed_ms_mean=42.989137`
- `elapsed_ms_min=38.957678`
- `candidate_count_mean=1200.0`
- `scandir_calls_mean=1.0`
- `path_glob_calls_mean=0.0`

## Candidate Result

Candidate after the itemgetter sort key change using the same registered probe settings:

- `elapsed_ms_mean=41.164483`
- `elapsed_ms_min=38.151258`
- `candidate_count_mean=1200.0`
- `scandir_calls_mean=1.0`
- `path_glob_calls_mean=0.0`

Delta: `-1.824654 ms` mean (`~4.24%` faster) for the scan metric in this local Linux probe run.
