# Maintenance Parameter Primitive Fast Path

## Scope

This Python-only performance slice narrows the hot benchmark-matrix parameter
normalization helpers in `MaintenanceCore`.

The helpers already accept arbitrary int/string-like objects for defensive test
coverage, but the runtime path receives exact protobuf `int` values and exact
Python `str` values. Calling `int(value)` or `str(value)` for those exact
primitive values repeats work on every benchmark-matrix dimension item.

## Optimization Hypothesis

Add exact-type fast paths in:

- `MaintenanceCore._positive_sorted_values()` for exact `int` values.
- `MaintenanceCore._normalized_string_values()` for exact `str` values.

This should preserve behavior for bools, subclasses, and custom convertible
objects while reducing per-item conversion overhead in the common primitive
runtime path.

## Probe Coverage

The affected path is covered by the registered PR-scoped probe:

- `maintenance-benchmark-parameter-normalization-single-convert`

This slice extends that probe with `native_elapsed_ms_mean`, a lower-is-better
metric that exercises exact primitive `int`/`str` inputs in addition to the
existing custom conversion-call checks.

## Verification Plan

Run focused Linux verification from the PR worktree:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_benchmark_helper_parsers_cover_invalid_and_boundary_inputs \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_maintenance_parameter_normalization_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_maintenance_parameter_normalization_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q <same focused tests>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/engine/maintenance_core.py \
  services/mlx-worker-python/tests/test_maintenance_service.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py \
  scripts/maintenance_benchmark_parameter_normalization_probe.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py \
  --registry infra/perf/pr_scoped_probes.json \
  --probe-id maintenance-benchmark-parameter-normalization-single-convert \
  --base-repo /root/.hermes/profiles/coder/workspace/melix \
  --head-repo "$PWD" \
  --output /tmp/maintenance_param_primitive_fastpath_probe.json
```

PR-scoped performance CI remains the final registered probe validation source
before merge.
