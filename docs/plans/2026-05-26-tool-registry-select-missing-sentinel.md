# Tool registry selection missing sentinel reuse

## Scope

This Python performance slice is limited to `worker.runtime.tool_registry.ToolRegistry.select()`.
It preserves tool-selection behavior, ordering, duplicate suppression, cache hits, and unknown-name
error reporting while avoiding a per-cache-miss `object()` allocation on the selected-name lookup path.

## Registered probe

The affected path is covered by the existing PR-scoped registered probe
`tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`. The registry entry
already includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/tool_registry.py`
- `services/mlx-worker-python/tests/test_tool_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/tool_registry_select_probe.py`

## Implementation plan

- Add a focused regression test proving unknown-name lookups reuse the same missing-name sentinel across
  calls rather than allocating a fresh sentinel object for each selection attempt.
- Extend the existing registered select probe with a missing-selection timing metric so this slice's
  affected path is measured by the PR-scoped performance workflow.
- Hoist the missing-tool sentinel to module scope and keep the existing single lookup pass unchanged.
- Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux.

## Validation boundary

This is a Python-only slice and is locally verifiable on Linux. CI must still run the registered
PR-scoped performance workflow before merge.
