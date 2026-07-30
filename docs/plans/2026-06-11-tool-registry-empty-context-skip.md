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

## 2026-07-17 Follow-up: Always-only receipt template

This incremental Python performance slice keeps the same registered `tool-registry-select-name-index-cache` probe. The default catalog always-only fallback now copies a precomputed receipt base and an isolated selected-tool payload instead of rebuilding the unchanged metrics fields for every no-keyword/whitespace fallback result. Behavior remains unchanged: callers still receive mutable per-call `receipt` and `selected_tools` objects, vector-enabled fallback receipts still preserve `vector_available=True`, and policy receipts continue through the existing full assembly path.

Expected metrics are lower `always_only_planning_elapsed_ms_mean`, `no_keyword_fallback_planning_elapsed_ms_mean`, and `whitespace_turn_planning_elapsed_ms_mean` in `scripts/tool_registry_select_probe.py`; selection/config metrics outside the always-only fallback path should remain stable.
