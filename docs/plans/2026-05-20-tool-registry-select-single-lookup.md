# Tool registry selection single lookup slice

## Scope

This Python performance slice is limited to `worker.runtime.tool_registry.ToolRegistry.select()`.
It preserves tool-selection behavior, ordering, duplicate suppression, and error reporting while reducing
per-selection name-index work after the selected name tuple has been normalized and cache misses.

## Registered probe

The affected path is covered by the existing PR-scoped registered probe
`tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`.
That registry entry already includes focused `test_command`, `coverage_command`, and `probe_command`
entries for:

- `services/mlx-worker-python/worker/runtime/tool_registry.py`
- `services/mlx-worker-python/tests/test_tool_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/tool_registry_select_probe.py`

## Implementation plan

- Add a focused regression test proving selected names are resolved through the cached name index once per
  selected name and without a separate membership pass.
- Replace the separate missing-name comprehension plus selected-tool comprehension with one explicit lookup
  pass that accumulates missing names for the existing error message.
- Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux.

## Validation boundary

This is a Python-only slice and is locally verifiable on Linux. CI must still run the registered
PR-scoped performance workflow before merge.
