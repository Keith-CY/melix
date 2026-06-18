# Tool Registry Keyword Empty-Fastpath Slice

## Scope

This Python-only performance slice is limited to the agentic tool selector keyword matching helper in `services/mlx-worker-python/worker/runtime/tool_registry.py`.

The selector calls `_keyword_tool_matches(...)` for the current turn and recent context during fallback keyword planning. Empty context should return immediately before case folding or boundary preparation. Whitespace-only context keeps the existing post-casefold strip guard so non-empty keyword traffic does not pay an added full-string scan.

## Registered Probe

The affected path is covered by the existing PR-scoped performance probe `tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`. That probe watches `tool_registry.py`, runs the focused tool registry regression tests, includes changed-scope coverage, and reports `selector_planning_elapsed_ms_mean` for `select_agentic_tools_for_turn(...)`.

## Implementation Plan

1. Keep behavior unchanged for empty, whitespace-only, literal, and boundary keyword matching inputs.
2. Add a fast return before `casefold()` for empty keyword text while preserving the existing whitespace-only guard after case folding.
3. Run the registered probe test command, coverage command, and probe command locally on Linux.
4. Use the PR-scoped performance workflow as the merge gate after push.

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_tool_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_tool_registry_schema_bytes_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_tool_registry_select_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_tool_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_tool_registry_schema_bytes_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_tool_registry_select_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/tool_registry.py services/mlx-worker-python/tests/test_tool_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/tool_registry_select_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/tool_registry_select_probe.py
```

## Acceptance

- Focused tool registry tests pass.
- Changed-scope coverage is at least 95%.
- The registered probe shows no selector planning regression; lower `selector_planning_elapsed_ms_mean` is the target metric.
- CI PR-scoped performance completes successfully before merge.
