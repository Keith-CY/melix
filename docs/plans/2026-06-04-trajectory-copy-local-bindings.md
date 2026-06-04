# Trajectory Provenance Copy Local Bindings Performance Slice

## Scope

This Python-only performance slice is limited to nested JSON container copying in
`services/mlx-worker-python/worker/trajectory_provenance.py`.

The registered PR-scoped probe `trajectory-provenance-copy-elision` already
covers the affected path with focused `test_command`, `coverage_command`, and
`probe_command` entries in `infra/perf/pr_scoped_probes.json`.

## Change

Keep trajectory provenance normalization semantics unchanged while reducing
container-dispatch overhead in `normalize_trajectory_provenance(...)`. The common
built-in `dict` and `list` values now use direct `type(...) is ...` checks before
falling back to the existing subclass-safe `isinstance(...)` path.

## Verification

Run the registered focused tests, changed-scope coverage, and registered probe
locally on Linux before opening the PR. Use GitHub Actions and the registered
PR-scoped performance workflow as the merge gate.

Success means behavior tests pass, changed-scope coverage remains at or above
95%, and the registered probe reports improved or explainably steady
`optimized_elapsed_ms_mean` / `elapsed_ms_mean` versus the pre-change local
baseline.
