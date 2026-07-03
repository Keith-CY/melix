# Tool registry selected-tool receipt single-pass assembly

## Summary

This Python-only performance slice keeps agentic tool selection behavior unchanged
while reducing per-call work in `select_agentic_tools_for_turn(...)`. Selection
already admits tools through `_append_selected_tool(...)`; this slice assembles the
receipt `selected_tools` entries during that admission pass so
`_build_tool_selection_result(...)` no longer rebuilds the same tool/source list
from `selected_names` plus the source lookup map.

## Registered PR-scoped probe

The affected path is covered by the registered PR-scoped performance probe
`tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`.
The entry already includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/tool_registry.py`
- `services/mlx-worker-python/tests/test_tool_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/tool_registry_select_probe.py`

No probe registry change is required for this slice. The registered probe
measures selector planning through `selector_planning_elapsed_ms_mean` and the
broader select path through `elapsed_ms_mean`.

## Optimization slice

Scope is limited to the selected-tool receipt assembly inside
`worker.runtime.tool_registry.select_agentic_tools_for_turn(...)`:

- pass a `selected_tools` receipt list through `_append_selected_tool(...)`;
- append the accepted `{"tool_id": ..., "source": ...}` receipt entry exactly
  when the tool is admitted;
- reuse that list in `_build_tool_selection_result(...)` instead of rebuilding it
  from `selected_names` and `selected_sources`.

The slice preserves keyword matching, vector selection, duplicate suppression,
receipt ordering, always-available tool admission, fallback semantics, and schema
byte metrics.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and the
registered probe locally on Linux. The PR-scoped performance workflow remains the
merge gate for base-vs-head validation.

## Success criteria

- Focused Python tests pass.
- Changed-scope coverage for touched files remains at or above 95%.
- Registered probe shows non-regressing or improved selector planning metrics.
- GitHub Actions and the PR-scoped performance workflow are green before merge.
