# Tool Selection Singleton Receipt Fast Path

## Slice

Optimize the Python agentic tool selection receipt builder for the common
single-tool result (`local_compute` only) without changing selection semantics.
This slice is intentionally limited to `worker/runtime/tool_registry.py`.

## Registered Probe

Affected path coverage uses the existing registered PR-scoped probe
`tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries and runs `scripts/tool_registry_select_probe.py`.

## Plan

1. Preserve the existing branch that skips optional keyword/vector scans when
   `max_selected_tools == 1`.
2. In `_build_tool_selection_result`, avoid tuple creation plus a list
   comprehension over `selected_registry.names()` when the normalized selected
   list contains exactly one tool.
3. Reuse `registry.select((selected_name,))` and build the one receipt entry
   directly from `selected_sources`.
4. Verify focused tests, changed-scope coverage, and the registered probe on
   Linux before creating the PR.

## Success Metrics

The registered probe should show a lower `always_only_planning_elapsed_ms_mean`
for the max-one-tool path, with no regression in selected schema bytes or
selection receipt behavior.
