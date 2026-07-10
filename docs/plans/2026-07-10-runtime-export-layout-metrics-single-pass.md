# Runtime Export Layout Metrics Single-Pass Aggregation

## Scope

Optimize the Python runtime export layout metrics path in
`services/mlx-worker-python/worker/productization/export_target_layout.py` by
aggregating retention report totals in one pass instead of running separate
`sum(...)` generator scans for each metric.

## Probe Coverage

The affected path is covered by the registered PR-scoped probe
`runtime-export-layout-retention` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for the export target layout module, retention tests,
PR-scoped performance tests, fixtures, and
`scripts/runtime_export_layout_retention_probe.py`.

## Behavior Contract

- Report keys and numeric values remain unchanged.
- Missing or non-numeric retention report metrics continue to resolve to `0`.
- Cleanup behavior and placeholder materialization are unchanged.

## Verification Plan

Run the registered focused tests, changed-scope coverage command, and registered
`runtime-export-layout-retention` probe locally on Linux. PR-scoped CI
performance validation remains the merge gate.
