# Local Job JSON Tuple7 Copy Fast Path

## Scope

This Python-only performance slice is limited to `_copy_json_like_value(...)` in
`services/mlx-worker-python/worker/runtime/local_job_continuation.py`. It extends
the existing exact scalar tuple fast paths from two through six elements to exact
seven-element scalar tuples that can appear in compact local-job follow-up
metadata. The change avoids generator construction for this tuple shape while
preserving recursive copy isolation for nested mutable tuple members.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`local-job-followup-scan-scandir` in `infra/perf/pr_scoped_probes.json`. The
probe has focused `test_command`, `coverage_command`, and `probe_command` entries
for:

- `services/mlx-worker-python/worker/runtime/local_job_continuation.py`
- `services/mlx-worker-python/tests/test_local_job_continuation.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/local_job_followup_scan_probe.py`

This slice extends the probe payload with a representative exact seven-item
scalar tuple and adds this plan to the probe watch list. No Swift runtime
behavior is changed.

## Verification plan

1. Run the registered focused local-job tests and registry/probe tests locally on
   Linux.
2. Run changed-scope coverage for the touched Python path, tests, probe script,
   and this plan; require at least 95% changed-line coverage.
3. Run the registered `local-job-followup-scan-scandir` probe locally on Linux
   against `origin/main` and this branch, comparing
   `scalar_copy_optimized_elapsed_ms_mean`, `scalar_copy_delta_ms`, and
   `scalar_copy_speedup`.
4. Use GitHub Actions PR-scoped performance as the final registered CI probe
   validation before merge.
