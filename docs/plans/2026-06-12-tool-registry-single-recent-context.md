# Tool registry single recent context fast path

This Python-only performance slice is limited to agentic tool keyword planning in
`worker.runtime.tool_registry.select_agentic_tools_for_turn`.

## Scope

- Preserve keyword fallback behavior for current and recent user turns.
- Avoid allocating a joined context string when there is exactly one recent user
  turn; the selector can scan that existing string directly.
- Keep multi-recent-turn behavior unchanged by continuing to join entries with a
  single space separator.

## Registered probe

The affected path is covered by `tool-registry-select-name-index-cache` in
`infra/perf/pr_scoped_probes.json`. The registered probe includes focused
`test_command`, `coverage_command`, and `probe_command` entries, and its
selector-planning sample includes the single-recent-turn keyword fallback case
this slice optimizes.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and
registered probe locally on Linux. GitHub Actions remains the merge gate for the
PR-scoped performance report after push.

## Expected metrics

`selector_planning_elapsed_ms_mean` should improve or remain neutral while the
overall select probe metrics stay neutral. The optimization removes one short
string join allocation from the common single-recent-context fallback path.
