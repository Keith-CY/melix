# Tool Registry OpenAI Template Loop

Date: 2026-05-24

## Scope

This Python-only performance slice is limited to `ToolRegistry.as_openai_tools()`
in `services/mlx-worker-python/worker/runtime/tool_registry.py`.

## Problem

The OpenAI tool payload hot path is already backed by cached descriptor
metadata, but each call still builds the per-tool `properties` dictionary through
an inner dictionary comprehension. The registered probe repeatedly materializes
OpenAI tool payloads and mutates the returned `required` list to prove call-level
isolation. On that small, repeated payload shape, the comprehension creates extra
frame overhead while the registry already has the cached property tuple needed
for a direct copy loop.

## Plan

- Keep the existing cached `_openai_tool_templates` source of truth.
- Replace only the inner `properties` dictionary comprehension with an explicit
  copy loop inside `ToolRegistry.as_openai_tools()`.
- Preserve returned payload equality and mutation isolation for schema property
  dictionaries and `required` lists.
- Use the existing registered PR-scoped probe
  `tool-registry-openai-tools-template-cache` for test, coverage, and metrics.

## Registered Probe

Registered PR-scoped probe: `tool-registry-openai-tools-template-cache` in
`infra/perf/pr_scoped_probes.json`.

Focused commands:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_tool_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_tool_registry_schema_bytes_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_tool_registry_openai_tools_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_tool_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_tool_registry_schema_bytes_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_tool_registry_openai_tools_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/tool_registry.py services/mlx-worker-python/tests/test_tool_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/tool_registry_openai_tools_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/tool_registry_openai_tools_probe.py
```

## Acceptance Criteria

- Focused behavior tests pass locally on Linux.
- Changed-scope coverage is at least 95% for the touched scope.
- The registered probe reports lower `elapsed_ms_mean` for repeated OpenAI tool
  materialization compared with `origin/main`.
- CI PR-scoped performance completes successfully before merge.
