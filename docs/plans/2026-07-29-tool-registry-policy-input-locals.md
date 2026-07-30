# Tool Registry Policy Input Locals Performance Slice

## Scope

This Python-only performance slice is limited to the policy-aware agentic tool selection path in `services/mlx-worker-python/worker/runtime/tool_registry.py`.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe `tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`. The registry entry watches `tool_registry.py`, the focused tool registry tests, PR-scoped performance tests, and `scripts/tool_registry_select_probe.py`, and it includes focused `test_command`, `coverage_command`, and `probe_command` entries.

## Optimization

`_select_agentic_tools_for_turn_with_policy(...)` now mirrors the non-policy selection path by binding the hot `ToolSelectionInput` fields (`vector_selected_tool_ids`, `recent_user_turns`, `vector_available`, and `current_user_turn`) once near entry and reusing those locals across the early fallback, vector, current-keyword, and context-keyword branches. Behavior remains unchanged; the slice only avoids repeated dataclass attribute reads in the policy selection hot path.

## Verification Plan

Run locally on Linux before PR:

1. Focused tool registry tests and PR-scoped performance dispatch tests from the registered probe.
2. Changed-scope coverage using the registered coverage command for `tool-registry-select-name-index-cache`.
3. Registered probe locally with `scripts/tool_registry_select_probe.py`, comparing the pre-change and post-change metrics with at least three samples.
4. `git diff --check`.

GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.
