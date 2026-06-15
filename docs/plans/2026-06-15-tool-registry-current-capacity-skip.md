# Tool registry current keyword capacity fast path

This Python-only performance slice is limited to agentic tool keyword planning in
`worker.runtime.tool_registry.select_agentic_tools_for_turn`.

## Scope

- Preserve keyword fallback behavior and selected-tool ordering.
- Add current-turn keyword matches before scanning recent-turn context.
- Skip recent-context keyword scanning when the always-available tool plus
  current-turn keyword matches already fill `max_selected_tools`.
- Keep vector-selected routing and always-only routing unchanged.

## Registered probe

The affected path is covered by `tool-registry-select-name-index-cache` in
`infra/perf/pr_scoped_probes.json`. The registered probe includes focused
`test_command`, `coverage_command`, and `probe_command` entries. This slice also
extends `scripts/tool_registry_select_probe.py` with a current-capacity sample so
the PR-scoped performance report records the optimized path directly.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and
registered probe locally on Linux. GitHub Actions remains the merge gate for the
PR-scoped performance report after push.

## Expected metrics

`current_capacity_planning_elapsed_ms_mean` should improve because the selector
no longer allocates or scans recent-context text when the current turn already
fills the requested tool capacity. Existing selector-planning metrics should stay
neutral.
