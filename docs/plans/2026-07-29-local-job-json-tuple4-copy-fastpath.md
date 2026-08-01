# Local Job JSON Tuple4 Copy Fast Path

## Scope

This Python-only performance slice is limited to `_copy_json_like_value(...)` in
`services/mlx-worker-python/worker/runtime/local_job_continuation.py`. The prior
local-job JSON copier already specialized exact two-item and three-item scalar
tuples; this slice adds the same direct-copy shape for exact four-item scalar
tuples that can appear in compact completion summary metadata. The change avoids
generator construction for that tuple shape while preserving recursive copy
isolation for nested mutable tuple members.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`local-job-followup-scan-scandir` in `infra/perf/pr_scoped_probes.json`. The
probe has focused `test_command`, `coverage_command`, and `probe_command` entries
for:

- `services/mlx-worker-python/worker/runtime/local_job_continuation.py`
- `services/mlx-worker-python/tests/test_local_job_continuation.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/local_job_followup_scan_probe.py`

This slice extends the probe payload with a representative exact four-item scalar
tuple and adds this plan to the probe watch list. No Swift runtime behavior is
changed.

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

## Follow-up Slice: Tuple10 Scalar Copy Fast Path

The 2026-08-01 follow-up keeps the same Python-only boundary and registered
`local-job-followup-scan-scandir` probe. The local-job JSON-like copier now adds
a direct exact ten-item scalar tuple path to match the probe's compact completion
summary payload, avoiding the generic tuple generator for that shape while still
recursively copying any non-scalar member.

Success is accepted only if the registered focused tests, changed-scope coverage,
and local Linux registered probe pass with neutral-to-lower scalar-copy timing;
GitHub Actions PR-scoped performance remains the merge gate before squash merge.
