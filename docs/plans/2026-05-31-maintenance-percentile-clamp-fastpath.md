# Maintenance percentile clamp fast path

## Scope

This Python-only performance slice is limited to percentile calculation in
`services/mlx-worker-python/worker/engine/maintenance_core.py`.

Benchmark reporting calls `_ordered_percentile()` repeatedly for already-sorted
latency vectors. The helper currently clamps percentile input with nested
`min()` / `max()` calls and reads the ordered vector length twice on the common
multi-value path. The slice keeps interpolation behavior unchanged while
reducing helper overhead.

## Registered probe

The affected path is covered by the existing PR-scoped performance probe
`maintenance-percentile-vector-reuse` in `infra/perf/pr_scoped_probes.json`.

The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` values for:

- `services/mlx-worker-python/worker/engine/maintenance_core.py`
- `services/mlx-worker-python/tests/test_maintenance_service.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

No probe registration change is required for this slice.

## Implementation plan

1. Preserve percentile interpolation, empty-list handling, singleton handling,
   and out-of-range percentile clamping.
2. Cache the ordered vector length once inside `_ordered_percentile()`.
3. Replace nested clamp helper calls with explicit branch clamping before rank
   calculation.
4. Run the registered focused tests, changed-scope coverage command, and
   registered probe locally on Linux before opening the PR.
5. Use the GitHub PR-scoped performance report as the merge gate.

## Local metrics plan

Compare `origin/main` and this branch with the registered
`maintenance-percentile-vector-reuse` probe settings. The accepted direction is
lower `elapsed_ms_mean` with unchanged percentile helper behavior and no
coverage loss.