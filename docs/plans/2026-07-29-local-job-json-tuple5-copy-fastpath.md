# Local Job JSON Tuple5 Copy Fast Path

## Scope

This Python-only performance slice is limited to `_copy_json_like_value(...)` in
`services/mlx-worker-python/worker/runtime/local_job_continuation.py`. It extends
the existing exact scalar tuple fast paths from two, three, and four elements to
exact five-element scalar tuples that can appear in compact local-job follow-up
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

This slice extends the probe payload with a representative exact five-item scalar
tuple. No Swift runtime behavior is changed.

## Follow-up Slice: Tuple6 Scalar Copy Fast Path

The tuple6 follow-up keeps `_copy_json_like_value(...)` behavior unchanged, but
extends the exact scalar tuple fast path to six-element scalar tuples. Compact
local-job follow-up receipts can carry short positional scalar tuples in metrics
and status metadata; this slice avoids generator construction for the six-item
shape while preserving recursive copy isolation whenever any tuple member is a
mutable JSON-like container.

Expected effect:

- reduce `local-job-followup-scan-scandir`
  `scalar_copy_optimized_elapsed_ms_mean` when the probe payload includes a
  representative scalar six-tuple;
- preserve recursive copy isolation for mixed tuple payloads;
- leave directory scanning, follow-up projection, receipt schema, and Swift
  runtime behavior unchanged.

## Verification plan

1. Run the registered focused local-job tests and registry/probe tests locally on
   Linux.
2. Run changed-scope coverage for the touched Python path, tests, and probe
   script; require at least 95% changed-line coverage.
3. Run the registered `local-job-followup-scan-scandir` probe locally on Linux
   against `origin/main` and this branch, comparing
   `scalar_copy_optimized_elapsed_ms_mean`, `scalar_copy_delta_ms`, and
   `scalar_copy_speedup`.
4. Use GitHub Actions PR-scoped performance as the final registered CI probe
   validation before merge.
