# Maintenance benchmark parameter empty-default fast path

## Scope

Optimize one Python hot path in `MaintenanceCore` benchmark parameter normalization:
when integer or string normalization produces no usable values, return the caller
provided default tuple before sorting an empty set.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`maintenance-benchmark-parameter-normalization-single-convert` in
`infra/perf/pr_scoped_probes.json`.

The probe already defines focused `test_command`, `coverage_command`, and
`probe_command` entries covering:

- `services/mlx-worker-python/worker/engine/maintenance_core.py`
- `services/mlx-worker-python/tests/test_maintenance_service.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/maintenance_benchmark_parameter_normalization_probe.py`

## Verification plan

1. Add regression assertions that empty integer and string normalization return
   the default tuple without invoking the module-level `sorted` lookup.
2. Run the registered focused test command locally on Linux.
3. Run the registered changed-scope coverage command locally on Linux.
4. Run the registered probe command locally on Linux and compare against the
   pre-change baseline.

## Expected behavior

Behavior remains unchanged for non-empty normalized values and for default
fallbacks. The slice only removes unnecessary empty-sort/list work on default
fallback paths.
