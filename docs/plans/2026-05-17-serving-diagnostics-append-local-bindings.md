# Serving Diagnostics Append Local Bindings Slice

## Goal

Reduce per-event overhead in `BoundedServingDiagnosticsEventQueue.append(...)` while preserving debug diagnostics queue retention and overflow semantics.

## Scope

- `services/mlx-worker-python/worker/productization/serving_diagnostics.py`
- `services/mlx-worker-python/tests/test_serving_diagnostics.py`

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe `serving-diagnostics-debug-queue-bounds` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries and runs on `ubuntu-latest`.

## Implementation Plan

1. Preserve queue append return semantics, retained snapshot length, and dropped-count behavior with existing focused serving diagnostics tests.
2. Hoist repeated saturated-append attribute lookups in `BoundedServingDiagnosticsEventQueue.append(...)` into local variables while keeping the same lock and `deque(maxlen=...)` behavior.
3. Run the registered focused tests, changed-scope coverage, and registered probe locally on Linux.
4. Use the PR-scoped performance workflow as the merge gate for the registered probe report.

## Metrics

Primary metric: `serving-diagnostics-debug-queue-bounds` `elapsed_ms_mean` (lower is better). Secondary metric: `serialization_elapsed_ms_mean` should not regress because serialization behavior is unchanged.
