# Tool registry selector field locals

## Goal

Reduce repeated dataclass attribute reads in `select_agentic_tools_for_turn()` while
preserving the existing tool-selection receipt semantics.

## Scope

This Python-only slice is limited to the non-policy selector path in
`services/mlx-worker-python/worker/runtime/tool_registry.py`. It keeps the
selection rules, fallback behavior, selected registry, and receipt payloads
unchanged.

## Registered probe

The affected path is already covered by the registered PR-scoped performance
probe `tool-registry-select-name-index-cache` in
`infra/perf/pr_scoped_probes.json`. That probe includes focused `test_command`,
`coverage_command`, and `probe_command` entries covering `tool_registry.py`, the
focused tool-registry tests, PR-scoped probe selection tests, and
`scripts/tool_registry_select_probe.py`.

## Implementation

- Snapshot the hot `ToolSelectionInput` fields into local variables at selector
  entry.
- Reuse those locals through vector, current-turn keyword, context keyword, and
  fallback-reason branches.
- Remove the unreachable `selection_mode != "vector"` guard after vector
  selection because successful vector selection returns immediately; unsuccessful
  vector selection must still continue to keyword fallback as before.

## Verification

- Run the focused registered test command locally on Linux.
- Run the changed-scope coverage command locally on Linux.
- Run `scripts/tool_registry_select_probe.py` before and after the change and
  compare `selector_planning_elapsed_ms_mean` plus adjacent selector metrics.
- Let the PR-scoped performance workflow validate the registered probe in CI
  before merging.
