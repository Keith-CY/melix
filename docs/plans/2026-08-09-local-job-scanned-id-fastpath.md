# Local job scanned id fast path

## Scope

This Python-only performance slice is limited to `LocalJobContinuationStore._load_scanned_record()` in `services/mlx-worker-python/worker/runtime/local_job_continuation.py`.

Large local-job follow-up scans already discover concrete record files through `os.scandir()` and pass the scanned file path into `_load_scanned_record()`. For ordinary path-safe job ids, the helper still re-entered the public `_safe_job_id()` normalization helper before opening the scanned path.

## Registered probe

The affected path is covered by the registered PR-scoped probe `local-job-followup-scan-scandir` in `infra/perf/pr_scoped_probes.json`. The entry includes focused `test_command`, `coverage_command`, and `probe_command` commands and reports scan timing, scandir/glob/exists counts, projection timing, and JSON-like copy helper metrics.

## Plan

1. Preserve fallback behavior for special or invalid scanned job ids by routing them through the existing public `load_record()` path.
2. For normal path-safe scanned job ids, validate with the already-compiled `JOB_ID_PATTERN` directly and open the scanned path without calling `_safe_job_id()` again.
3. Keep the change isolated to scanned-record loading; do not alter scan ordering, receipt construction, or claim behavior.
4. Run focused local-job continuation tests, changed-scope coverage, and the registered local-job follow-up scan probe locally on Linux before pushing. GitHub Actions PR-scoped performance remains the merge gate after PR creation.

## Success criteria

- Focused local-job continuation tests pass.
- Changed-scope coverage remains at least 95 percent for the touched scope.
- The registered probe shows lower or non-regressing `elapsed_ms_mean` while keeping `scandir_calls_mean`, `path_glob_calls_mean`, and `path_exists_calls_mean` unchanged.