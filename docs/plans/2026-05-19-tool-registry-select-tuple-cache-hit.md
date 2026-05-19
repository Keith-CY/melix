# Tool registry tuple cache-hit fast path

## Summary

This performance slice keeps `ToolRegistry.select()` behavior unchanged while
short-circuiting repeated clean tuple selections that already exist in the
selection cache.

## Registered PR-scoped probe

The affected path is covered by the registered PR-scoped performance probe
`tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/tool_registry.py`
- `services/mlx-worker-python/tests/test_tool_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/tool_registry_select_probe.py`

No new probe registry entry is required for this slice.

## Optimization slice

`ToolRegistry.select()` already normalizes requested names, deduplicates them,
validates missing names, and caches selected registries by the normalized tuple.
The registered probe repeatedly calls `select()` with clean tuple selections.
After the first selection builds the cached registry, later identical tuple
calls can safely probe `_selection_cache` before rebuilding the normalized tuple
or touching the name index.

The fast path is intentionally limited to tuple inputs:

- complete tuple selections equal to `self._tool_names` return `self` directly;
- cached clean tuple selections return the cached registry directly;
- list inputs, blank trimming, deduplication, missing-name errors, and cache
  population continue through the existing normalization path.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and
registered probe locally on Linux. The PR-scoped performance workflow must also
select and complete `tool-registry-select-name-index-cache` before merge.

## Success criteria

- Focused Python tests pass.
- Changed-scope coverage for the touched files remains at or above 95%.
- Registered probe shows a clear reduction in `elapsed_ms_mean` for repeated
  tuple cache hits.
- GitHub Actions and the PR-scoped performance workflow are green.
