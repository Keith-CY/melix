# Trajectory scalar list exact-copy performance slice

## Scope

This Python-only performance slice is limited to `worker.trajectory_provenance._copy_json_list()` for exact `list` instances that contain only JSON-immutable scalar values.

## Registered probe

The affected file is covered by the registered PR-scoped performance probe `trajectory-provenance-copy-elision` in `infra/perf/pr_scoped_probes.json`. The probe watches:

- `services/mlx-worker-python/worker/trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/trajectory_provenance_copy_elision_probe.py`

The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` fields. Local Linux verification uses those commands before PR creation; GitHub Actions PR-scoped performance remains the merge gate.

## Implementation plan

1. Preserve the recursive-copy and custom-list-subclass behavior already covered by tests.
2. Use the unbound built-in `list.copy(value)` path after the immutable scan instead of a list display copy.
3. Keep list subclasses safe by calling the built-in descriptor directly, so overridden `copy()` methods are not invoked and the result remains an exact `list`.
4. Run the registered focused tests, changed-scope coverage command, and local probe.
5. Create and merge a focused PR only after CI and the registered PR-scoped performance report pass.

## Success criteria

- Focused trajectory provenance tests pass.
- Changed-scope coverage for `worker.trajectory_provenance` remains above the repository threshold.
- `trajectory-provenance-copy-elision` reports lower or equivalent scalar-list elapsed time and no in-scope regression.
