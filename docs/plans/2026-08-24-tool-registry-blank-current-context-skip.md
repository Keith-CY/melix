# Tool Registry Blank Current Context Scan Skip

## Scope

This Python-only performance slice is limited to
`worker.runtime.tool_registry.select_agentic_tools_for_turn(...)` when the
current user turn is blank but recent user turns are available for keyword
selection.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`.
This slice keeps the existing focused `test_command`, `coverage_command`, and
`probe_command`, and adds a dedicated
`blank_current_context_planning_elapsed_ms_mean` probe metric for the blank
current-turn plus recent-context case.

## Implementation plan

1. Preserve fallback behavior for completely blank/no-context turns.
2. Skip the current-turn `_keyword_tool_matches(...)` call when the current turn
   is empty or whitespace-only, then scan recent context directly when present.
3. Add a regression test proving only the recent context is scanned for blank
   current turns.
4. Verify focused tool-registry tests, changed-scope coverage, and the
   registered probe locally on Linux before using PR-scoped CI as the merge
   gate.

## Success criteria

- Tool selection behavior and selected schema bytes remain unchanged.
- The registered probe reports lower or stable
  `blank_current_context_planning_elapsed_ms_mean`.
- Changed-scope coverage for touched Python files remains above the repository
  threshold.
