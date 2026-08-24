# Maintenance benchmark parameter builtin bindings

## Scope

This Python-only performance slice is limited to benchmark parameter normalization
helpers in `services/mlx-worker-python/worker/engine/maintenance_core.py`:

- `MaintenanceCore._positive_sorted_values(...)`
- `MaintenanceCore._normalized_string_values(...)`

The behavior remains unchanged: values are normalized once, non-positive/blank
values are skipped, defaults are returned for empty normalized sets, singleton
sets avoid sorting, and multi-value sets return sorted tuples.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`maintenance-benchmark-parameter-normalization-single-convert` in
`infra/perf/pr_scoped_probes.json`.

The probe entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for the maintenance benchmark parameter helpers, their
focused tests, and `scripts/maintenance_benchmark_parameter_normalization_probe.py`.

## Optimization slice

The helpers already avoid duplicate conversion of counted `int`/`str`-like
objects. This slice keeps that contract and binds the hot builtins (`type`,
`int`, `str`, and `str.strip`) as function defaults so repeated native benchmark
parameter scans avoid module/builtin lookups inside the per-value loop.

## Verification plan

Run the registered focused test command, the registered changed-scope coverage
command, and the registered probe locally on Linux. GitHub Actions PR-scoped
performance remains the merge gate after the PR opens.

## Linux verification boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
effect is claimed.
