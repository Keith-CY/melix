# Evaluation latency max from sorted vector

## Goal

Reduce a small repeated scan in `EvaluationCore._latency_stats()` by reusing the sorted latency vector for the max value after percentile calculation.

## Scope

- `services/mlx-worker-python/worker/engine/evaluation_core.py`
- `services/mlx-worker-python/tests/test_evaluation_core.py`
- `infra/perf/pr_scoped_probes.json`

## Registered probe

The affected path is already covered by the `evaluation-latency-percentile-vector-reuse` PR-scoped probe in `infra/perf/pr_scoped_probes.json`:

- `watch_globs` includes `services/mlx-worker-python/worker/engine/evaluation_core.py`, `services/mlx-worker-python/tests/test_evaluation_core.py`, and the PR-scoped performance tests.
- `test_command` runs the focused latency-stat behavior tests and probe selection/command checks.
- `coverage_command` measures changed-scope coverage for `evaluation_core.py`, `test_evaluation_core.py`, and `test_pr_scoped_performance.py`.
- `probe_command` exercises `_latency_stats()` across a 12,000-value vector for 160 iterations and records elapsed time plus sorted-call count.

## Implementation plan

1. Keep percentile behavior unchanged by continuing to sort once and pass the ordered vector to `_ordered_percentile()`.
2. Reuse `sorted_values[-1]` for the maximum instead of scanning the original vector with `max(values)`.
3. Reuse the sorted-vector length for mean division to avoid a second `len(values)` call.
4. Verify with focused tests, changed-scope coverage, and the registered probe against `origin/main`.

## Success metrics

The registered `evaluation-latency-percentile-vector-reuse` probe should keep `sorted_calls_mean` at `1.0`, preserve p50/p95 results, and show a lower `elapsed_ms_mean` versus the `origin/main` baseline.
