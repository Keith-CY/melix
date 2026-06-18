# Tool Registry Always-Only Selection Fast Path Performance Slice

## Scope

This slice optimizes `select_agentic_tools_for_turn()` when `max_selected_tools`
normalizes to one. In that case the always-available `local_compute` tool fills
all available selection capacity, so vector and keyword routing cannot add any
other tool. Behavior remains unchanged: the returned receipt still reports
fallback selection with `local_compute` sourced from `always`.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`.
That probe includes focused tool-registry behavior tests, changed-scope coverage,
and `scripts/tool_registry_select_probe.py`, which reports the always-only
planning path as `always_only_planning_elapsed_ms_mean` alongside the broader
selection/config metrics.

## Verification plan

- Run the registered focused test command for tool registry selection behavior
  and PR-scoped probe coverage.
- Run the registered changed-scope coverage command.
- Run `scripts/tool_registry_select_probe.py` locally on Linux before and after
  the change, with repeated samples, and compare the always-only planning metric.
- Rely on GitHub Actions PR-scoped performance workflow for the final registered
  CI probe report before merge.

## Expected outcome

Short-circuiting before the per-call closure/list setup avoids work on prompts
where tool-selection capacity is already exhausted by the always-available tool.
The improvement should be most visible in
`always_only_planning_elapsed_ms_mean`; other selector paths should remain within
normal noise.
