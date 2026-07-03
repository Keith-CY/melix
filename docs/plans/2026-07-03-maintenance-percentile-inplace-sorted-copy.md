# Maintenance Percentile Sorted-Copy Slice

## Scope

This Python-only performance slice is limited to `MaintenanceCore._percentiles()` and the shared `_ordered_percentile()` helper in `services/mlx-worker-python/worker/engine/maintenance_core.py`.

## Registered probe

The affected path is already covered by the registered PR-scoped probe `maintenance-percentile-vector-reuse` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` values for the maintenance percentile path and its tests.

## Change

`_percentiles()` still preserves caller list order and reuses one ordered vector for all requested percentiles, but builds that vector with `values.copy()` followed by `list.sort()` instead of `builtins.sorted(values)`. This keeps the same semantics while avoiding the global `sorted` call on the hot path that is repeatedly exercised by benchmark summary generation.

`_ordered_percentile()` now derives the lower interpolation index with `int(rank)` and only reads the upper neighbor when interpolation is required. This removes the extra `math.floor()`/`math.ceil()` calls without changing percentile clamping or interpolation results.

## Validation

1. Run the registered focused tests for `maintenance-percentile-vector-reuse`.
2. Run changed-scope coverage for the same registered probe.
3. Run the registered probe locally on Linux and compare against an `origin/main` baseline.

## Success criteria

- Focused maintenance percentile tests pass.
- Changed-scope coverage remains at or above 95%.
- Registered probe preserves percentile values and reduces the tracked `sort_calls_mean` for `_percentiles()` from one builtins `sorted()` call per iteration to zero.
