# Tool registry metrics snapshot cache slice

## Goal

Reduce repeated aggregate work in `worker.runtime.tool_registry.ToolRegistry.metrics()`.
The descriptor-level schema byte cache removes repeated JSON encoding, but each metrics call still iterates over every tool and required-argument tuple. This slice stores the immutable registry metrics snapshot once during `ToolRegistry` construction and returns it directly for repeated calls.

## Scope

- Python-only runtime change in `services/mlx-worker-python/worker/runtime/tool_registry.py`.
- Focused unit coverage in `services/mlx-worker-python/tests/test_tool_registry.py`.
- Existing registered PR-scoped probe coverage through `tool-registry-schema-bytes-cache` in `infra/perf/pr_scoped_probes.json`.
- No protocol schema, generated artifact, dependency, Swift, or macOS runtime changes.

## Probe

Registered PR-scoped probe: `tool-registry-schema-bytes-cache`.

The probe measures repeated `ToolRegistry.metrics()` calls over the built-in agentic tool registry and reports:

- `elapsed_ms_mean`: wall-clock time for repeated metrics calls.
- `json_schema_calls_mean`: calls to `ToolDescriptor.json_schema()` during metrics collection; the optimized path remains `0.0`.
- `schema_byte_count_calls_mean`: calls to `ToolDescriptor.schema_byte_count()` during repeated metrics collection; this slice targets `0.0` after the registry snapshot has been constructed.

## Verification Plan

Run the registered focused command set locally on Linux before opening the PR:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_tool_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_tool_registry_schema_bytes_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_tool_registry_schema_bytes_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_tool_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_tool_registry_schema_bytes_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_tool_registry_schema_bytes_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/tool_registry.py services/mlx-worker-python/tests/test_tool_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/tool_registry_schema_bytes_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/tool_registry_schema_bytes_probe.py
```

CI PR-scoped performance remains the merge gate for the registered probe report.
