# Serving Diagnostics Queue Overflow Fast Path

## Scope

This Python-only slice optimizes the debug serving diagnostics event queue and
the high-frequency event objects it stores. After the queue reaches its
configured bound, every later append is also an overflow, so the queue can reuse
that state instead of rechecking the current deque length on each saturated
append. The queue object, event objects, and snapshots use explicit slots so the
debug buffer does not carry unnecessary per-instance dictionaries.

This follow-up slice keeps the same immutable `ServingDiagnosticsEvent` public
contract but supplies a module-cached local-binding initializer for the frozen
slots dataclass. The registered probe constructs thousands of events per sample,
so avoiding the generated initializer's repeated global `object.__setattr__`
lookups targets the dominant local Linux cost without changing serialized
diagnostics payloads.

## Affected Paths

- `services/mlx-worker-python/worker/productization/serving_diagnostics.py`
- `services/mlx-worker-python/tests/test_serving_diagnostics.py`
- `scripts/serving_diagnostics_queue_probe.py`

## Registered Probe

The affected path is covered by the existing
`serving-diagnostics-debug-queue-bounds` PR-scoped performance probe in
`infra/perf/pr_scoped_probes.json`. The registered entry includes focused
`test_command`, `coverage_command`, and `probe_command` values and reports:

- `elapsed_ms_mean` (`lower_is_better`)
- `serialization_elapsed_ms_mean` (`lower_is_better`)
- `dropped_count` (`informational`)
- `retained_count` (`informational`)

## Verification Plan

Run the registered focused pytest command, changed-scope coverage command, and
local Linux probe before opening the PR. The GitHub PR-scoped performance
workflow remains the merge gate for the registered probe report.
