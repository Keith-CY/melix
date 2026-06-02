# Tool registry select single-pass normalized lookup

## Summary

This Python-only performance slice keeps `ToolRegistry.select()` behavior unchanged
while reducing work on uncached multi-name selections. The current path first
normalizes and deduplicates requested names, then performs a second pass over the
normalized tuple to look up descriptors and collect missing names. This slice
combines normalization, deduplication, descriptor lookup, and missing-name
collection into one pass while preserving the normalized tuple cache key and
existing raw tuple cache aliases.

## Registered PR-scoped probe

The affected path is covered by the registered PR-scoped performance probe
`tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`.
The entry already includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/tool_registry.py`
- `services/mlx-worker-python/tests/test_tool_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/tool_registry_select_probe.py`

No probe registry change is required for this slice.

## Optimization slice

Scope is limited to `ToolRegistry.select()` multi-name misses before a selected
registry is cached:

- keep exact tuple and exact full-list fast paths unchanged;
- keep single-name handling unchanged;
- build `requested_names`, `selected`, and `missing_names` during the same loop;
- preserve duplicate-name elision, blank-name elision, missing-name errors,
  selected registry ordering, and cache population semantics.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and the
registered probe locally on Linux. The PR-scoped performance workflow remains the
merge gate for base-vs-head validation.

## Success criteria

- Focused Python tests pass.
- Changed-scope coverage for touched files remains at or above 95%.
- Registered probe shows a non-regressing or improved `elapsed_ms_mean` and no
  semantic metric regressions.
- GitHub Actions and the PR-scoped performance workflow are green before merge.
