# Local Job JSON Tuple3 Copy Fast Path

## Scope

This Python-only performance slice narrows `_copy_json_like_value(...)` for the
local-job follow-up projection path. The prior slice specialized exact two-item
tuples; this slice adds the same direct-copy shape for exact three-item tuples,
which appear in compact phase/status metadata carried by completion summaries and
receipts. The change avoids generator construction for that common tuple shape
while preserving recursive copy isolation for nested mutable values.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`local-job-followup-scan-scandir` in `infra/perf/pr_scoped_probes.json`. The
probe has focused `test_command`, `coverage_command`, and `probe_command` entries
for:

- `services/mlx-worker-python/worker/runtime/local_job_continuation.py`
- `services/mlx-worker-python/tests/test_local_job_continuation.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/local_job_followup_scan_probe.py`

This slice extends the probe payload with a representative exact three-item tuple
and adds this plan to the probe watch list. No Swift runtime behavior is changed.

## Verification plan

1. Run the registered focused local-job tests and registry/probe tests locally on
   Linux.
2. Run changed-scope coverage for the touched Python path and tests; require at
   least 95% changed-line coverage.
3. Run the registered `local-job-followup-scan-scandir` probe locally on Linux
   against `origin/main` and this branch, comparing `scalar_copy_optimized_elapsed_ms_mean`,
   `scalar_copy_delta_ms`, and `scalar_copy_speedup`.
4. Use GitHub Actions PR-scoped performance as the final registered CI probe
   validation before merge.

## 2026-07-15 follow-up: JSON scalar-copy type binding

This Python-only follow-up remains limited to `_copy_json_like_value(...)` in the
local-job follow-up projection path. The copier now reuses a function-local
`type` binding across the exact dict/list scalar scans instead of resolving the
builtin for every nested item. The change preserves scalar reuse, recursive copy
isolation for nested mutables, tuple fast paths, and container-subclass fallback
behavior. The registered `local-job-followup-scan-scandir` probe remains the
Linux and CI validation gate, with `scalar_copy_optimized_elapsed_ms_mean`,
`scalar_copy_delta_ms`, and `scalar_copy_speedup` as the primary metrics.
