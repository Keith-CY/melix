# MCP client metrics snapshot slots

## Scope

This Python-only performance slice is limited to the MCP client lifecycle metrics
containers in `services/mlx-worker-python/worker/runtime/mcp_client.py`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`mcp-client-typed-lifecycle-dispatch` in `infra/perf/pr_scoped_probes.json`. The
registry entry already provides focused `test_command`, `coverage_command`, and
`probe_command` entries for the MCP client lifecycle path, its focused tests, and
`scripts/mcp_client_lifecycle_probe.py`.

## Optimization

`MCPClientManager.metrics_snapshot()` creates a top-level metrics snapshot and
four operation snapshots each time diagnostics export metrics. The operation
counter object is also allocated for every manager. This slice keeps the same
fields and frozen snapshot behavior but adds dataclass slots to:

- `MCPOperationMetricsSnapshot`
- `MCPClientMetricsSnapshot`
- `_MutableMCPOperationMetrics`

The change removes per-instance `__dict__` allocation from the metrics hot path
without changing public field names, constructor order, or average-latency
semantics.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and the
registered probe locally on Linux before opening the PR. GitHub Actions
PR-scoped performance remains the merge gate for the registered probe report.