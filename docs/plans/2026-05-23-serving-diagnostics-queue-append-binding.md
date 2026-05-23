# Serving diagnostics queue append binding slice

## Scope

This Python-only performance slice targets `BoundedServingDiagnosticsEventQueue.append(...)` in `services/mlx-worker-python/worker/productization/serving_diagnostics.py`.

The affected path is covered by the registered PR-scoped performance probe `serving-diagnostics-debug-queue-bounds` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for the serving diagnostics implementation, tests, and `scripts/serving_diagnostics_queue_probe.py`.

## Optimization

The saturated debug queue path appends thousands of diagnostics events while holding the queue lock. This slice binds the deque append method to a local variable before the branch, then reuses that local for both retained and saturated appends. The queue capacity, drop-count semantics, snapshot shape, and serialized bundle payloads remain unchanged.

## Verification plan

1. Run the focused serving diagnostics tests and PR-scoped probe registry tests.
2. Run changed-scope coverage for the touched implementation, tests, registry test, and probe script.
3. Run the registered `serving-diagnostics-debug-queue-bounds` probe locally on Linux before and after the change with repeated samples.
4. Let the PR-scoped performance workflow validate the registered probe in CI before merge.

## Metrics

Primary metric: `elapsed_ms_mean` from `serving-diagnostics-debug-queue-bounds` (lower is better). Secondary metric: `serialization_elapsed_ms_mean` should not regress materially because serialization behavior is unchanged.
