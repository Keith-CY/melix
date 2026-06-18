# Tool registry keyword match cache

This Python-only performance slice keeps the agentic tool keyword-selection
behavior unchanged while avoiding repeated keyword scans for repeated prompts in
selector planning.

Registered PR-scoped probe: `tool-registry-select-name-index-cache` in
`infra/perf/pr_scoped_probes.json`. The probe covers
`services/mlx-worker-python/worker/runtime/tool_registry.py`, includes focused
`test_command`, `coverage_command`, and `probe_command` entries, and reports the
`selector_planning_elapsed_ms_mean` metric for `select_agentic_tools_for_turn`.

## Slice

1. Add a bounded `lru_cache(maxsize=128)` to `_keyword_tool_matches`, keyed by
   the original prompt/context string.
2. Preserve existing keyword semantics: empty text, whitespace-only text,
   literal hints, and boundary-token hints still return the same matches.
3. Add a regression test proving repeated keyword matching reuses the bounded
   cache without changing returned matches.

## Verification plan

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_tool_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_tool_registry_schema_bytes_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_tool_registry_select_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_tool_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_tool_registry_schema_bytes_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_tool_registry_select_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/tool_registry.py services/mlx-worker-python/tests/test_tool_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/tool_registry_select_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/tool_registry_select_probe.py
```

## Expected metrics

The primary metric is `selector_planning_elapsed_ms_mean` from
`scripts/tool_registry_select_probe.py`; repeated selector prompts in the probe
should hit the keyword-match cache after the first sample. General
`elapsed_ms_mean` registry-selection metrics may remain within noise because the
`ToolRegistry.select()` code path is unchanged.
