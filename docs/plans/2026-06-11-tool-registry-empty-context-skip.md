# Tool Registry Empty Context Keyword Scan Skip

## Goal

Avoid a redundant keyword matcher call in `select_agentic_tools_for_turn(...)` when no recent user turns are available. The default selector path is exercised for every agentic tool planning request, and the empty-context case is common for first-turn or vector-disabled requests.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe `tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`. The probe watches `services/mlx-worker-python/worker/runtime/tool_registry.py`, the focused tool registry tests, and `scripts/tool_registry_select_probe.py`; it includes `test_command`, `coverage_command`, and `probe_command` entries.

## Slice

1. Add a focused regression test proving empty `recent_user_turns` does not invoke `_keyword_tool_matches("")`.
2. Keep non-empty recent-turn behavior unchanged by joining and scanning context only when `recent_user_turns` is non-empty.
3. Verify with the focused test suite, changed-scope coverage, and the registered probe locally on Linux.

## Expected Metrics

The primary expected metric is a lower `selector_planning_elapsed_ms_mean` in the registered `tool_registry_select_probe.py` workload. Other select/config metrics should remain stable because the slice only affects the selector planning branch.
