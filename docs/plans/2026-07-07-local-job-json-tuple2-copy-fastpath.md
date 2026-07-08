# Local Job JSON Tuple2 Copy Fast Path

## Scope

This Python-only performance slice narrows `_copy_json_like_value(...)` for the local-job follow-up projection path. Completion summaries commonly carry compact coordinate-like tuples such as `(label, metadata)`. The slice adds an exact `tuple` length-two branch so the copier avoids constructing a generator for that common shape while preserving recursive isolation for nested mutable values.

## Registered probe

The affected path is covered by the registered PR-scoped probe `local-job-followup-scan-scandir` in `infra/perf/pr_scoped_probes.json`. The probe already includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/local_job_continuation.py`
- `services/mlx-worker-python/tests/test_local_job_continuation.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/local_job_followup_scan_probe.py`

This slice keeps that registered probe as the merge gate and adds this plan to the probe watch list.

## Verification plan

1. Run the registered focused local-job tests and registry/probe tests.
2. Run changed-scope coverage for the touched Python path and tests; require at least 95% changed-line coverage.
3. Run `scripts/local_job_followup_scan_probe.py` locally on Linux and compare `scalar_copy_optimized_elapsed_ms_mean`, `scalar_copy_delta_ms`, `scalar_copy_speedup`, and projection elapsed metrics against the pre-change baseline.
4. Use GitHub Actions PR-scoped performance as the final registered CI probe validation before merge.

## Expected outcome

The scalar-copy metric should improve because `_copy_json_like_value(...)` no longer pays tuple-generator overhead for two-item tuple metadata. The scan-only metrics are expected to remain within normal filesystem noise because this slice does not change candidate discovery or record reconciliation semantics.
