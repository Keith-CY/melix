# Serving Diagnostics Queue Overflow Fast Path

## Scope

This Python-only slice optimizes the debug serving diagnostics event queue after
it reaches its configured bound. The queue is append-only for a request bundle,
so once the first event has been dropped every later append is also an overflow.
The implementation can reuse that state instead of rechecking the current deque
length on each saturated append. The queue object also uses explicit slots so
this high-frequency debug buffer does not carry a per-instance dictionary.

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
- `dropped_count` (`informational`)
- `retained_count` (`informational`)

## Verification Plan

Run the registered focused pytest command, changed-scope coverage command, and
local Linux probe before opening the PR. The GitHub PR-scoped performance
workflow remains the merge gate for the registered probe report.
