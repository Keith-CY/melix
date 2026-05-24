# Tool registry select sentinel performance slice

## Scope

This Python-only performance slice keeps `ToolRegistry.select()` behavior unchanged while removing a per-call sentinel allocation from the requested-name lookup loop.

Affected files:

- `services/mlx-worker-python/worker/runtime/tool_registry.py`
- `docs/plans/2026-05-24-tool-registry-select-sentinel-performance.md`

## Registered probe

The affected path is covered by the registered PR-scoped probe `tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`. The registry entry already includes focused `test_command`, `coverage_command`, and `probe_command` commands for the tool-registry selection path.

## Implementation plan

1. Run the registered probe on `origin/main` to capture the local Linux baseline.
2. Promote the missing-tool sentinel used by `ToolRegistry.select()` from a fresh `object()` per normalized selection to a module-level singleton.
3. Run the focused tool-registry tests, changed-scope coverage, and registered probe locally on Linux.
4. Use the PR-scoped performance workflow as the merge gate after push.

## Expected behavior

- Unknown selected tool names still raise `ToolRegistryError` with the same missing-name list.
- Selected registries, raw tuple aliases, cache bounds, and full-list fast paths are unchanged.
- The registered probe should show a neutral-to-improved `elapsed_ms_mean` for repeated selection calls.

## Validation commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_tool_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_tool_registry_schema_bytes_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_tool_registry_select_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_tool_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_tool_registry_schema_bytes_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_tool_registry_select_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/tool_registry.py services/mlx-worker-python/tests/test_tool_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/tool_registry_select_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/tool_registry_select_probe.py
```
