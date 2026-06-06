# Trajectory Provenance Normalize Dispatch Slice

## Scope

This Python-only performance slice is limited to `normalize_trajectory_provenance()` in `services/mlx-worker-python/worker/trajectory_provenance.py`.

## Registered Probe

The affected path is already covered by registered PR-scoped probe `trajectory-provenance-copy-elision` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` fields and watches:

- `services/mlx-worker-python/worker/trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/trajectory_provenance_copy_elision_probe.py`

## Optimization Plan

Keep behavior equivalent while reducing per-field normalization overhead:

1. Bind the provenance getter and nested copy helper once per normalization call.
2. Dispatch by exact value type before checking the empty-string sentinel so dict/list values do not pay container-to-string equality work.
3. Preserve nested container copy isolation for JSON-like dict/list provenance values and keep the fallback for custom mutable values in `_copy_trajectory_provenance_value()`.

## Verification

Run the registered focused test command, changed-scope coverage command, and registered probe locally on Linux. GitHub Actions PR-scoped performance remains the final merge gate for the base-vs-head registered report.
