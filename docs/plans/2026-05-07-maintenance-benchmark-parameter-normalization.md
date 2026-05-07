# Maintenance benchmark parameter normalization single-convert plan

## Goal

Reduce redundant conversion work in benchmark matrix parameter normalization by converting each value at most once while preserving existing ordering, de-duplication, and fallback semantics.

## Linux-only constraint

This slice touches Python worker code and is verifiable on Linux with focused pytest, changed-scope coverage, and a PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/engine/maintenance_core.py`
- `services/mlx-worker-python/tests/test_maintenance_service.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/maintenance_benchmark_parameter_normalization_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Performance probe

Register `maintenance-benchmark-parameter-normalization-single-convert` in the PR-scoped performance registry.

The probe repeatedly normalizes synthetic integer and string benchmark parameter values and reports:

- `elapsed_ms_mean` — lower is better.
- `calls_per_value_mean` — lower is better; the optimized path should be `1.0` conversion per input value.
- `peak_bytes_mean` — informational.

## Success metrics

- Focused parser tests pass.
- Changed executable coverage for touched Python scope is at least 95%.
- Local probe shows `calls_per_value_mean=1.0` on the optimized branch and concrete elapsed/peak metrics.
- `git diff --check` passes.
