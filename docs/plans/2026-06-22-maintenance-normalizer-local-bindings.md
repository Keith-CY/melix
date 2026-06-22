# Maintenance benchmark normalizer local bindings

## Scope

Optimize one Python hot path in `MaintenanceCore` benchmark parameter normalization:
cache the per-call `set.add` methods and string `strip` descriptor in local
variables while preserving the existing one-conversion-per-input behavior.

This slice is intentionally limited to:

- `MaintenanceCore._positive_sorted_values(...)`
- `MaintenanceCore._normalized_string_values(...)`

No benchmark matrix behavior, default fallback behavior, sorting order, or error
handling changes.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`maintenance-benchmark-parameter-normalization-single-convert` in
`infra/perf/pr_scoped_probes.json`.

The registry entry already defines focused `test_command`, `coverage_command`,
and `probe_command` values for:

- `services/mlx-worker-python/worker/engine/maintenance_core.py`
- `services/mlx-worker-python/tests/test_maintenance_service.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/maintenance_benchmark_parameter_normalization_probe.py`

## Verification plan

1. Run the focused helper/parser regression test command from the registered
   probe locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux.
3. Run the registered PR-scoped performance probe locally against `origin/main`
   and this branch.
4. Use the GitHub Actions PR-scoped performance report as the merge gate.

## Expected behavior

The helpers still return de-duplicated sorted positive integers or non-empty
trimmed strings, still return the provided default tuple when no values survive,
and still convert non-native `int`/`str` inputs exactly once per input.
