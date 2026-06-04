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
built-in `dict` and `list` values already use direct `type(...) is ...` checks
before falling back to the existing subclass-safe `isinstance(...)` path.

This follow-up micro-slice keeps the same registered probe and narrows the next
hot path inside `_copy_trajectory_provenance_value(...)`: keep the existing exact
`type(...) is ...` dispatch order, but use a precomputed frozenset for exact JSON
scalar type membership before falling back to subclass-safe `isinstance(...)` and
`copy.deepcopy(...)` handling. This targets the leaf-heavy recursive copy path
without changing container isolation semantics.

## Verification

Run the registered focused tests, changed-scope coverage, and registered probe
locally on Linux before opening the PR. Use GitHub Actions and the registered
PR-scoped performance workflow as the merge gate.

Success means behavior tests pass, changed-scope coverage remains at or above
95%, and the registered probe reports improved or explainably steady
`optimized_elapsed_ms_mean` / `elapsed_ms_mean` versus the pre-change local
baseline.
