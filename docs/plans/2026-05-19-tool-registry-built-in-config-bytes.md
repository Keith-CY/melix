# Tool Registry Built-in Config Bytes Cache Plan

## Goal

Reduce repeated built-in tool configuration construction cost for the default
agentic tool path. The hot call is `built_in_tool_config()` with no explicit
name filter, which currently rebuilds a `ToolRegistry` and serializes each tool
schema for every call.

## Linux-Only Constraint

This is a Python-only runtime slice under `services/mlx-worker-python` and is
fully verifiable on Linux with focused pytest, changed-scope coverage, and the
registered PR-scoped performance probe.

## Touched Files

- `services/mlx-worker-python/worker/runtime/tool_registry.py`
- `services/mlx-worker-python/tests/test_tool_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/tool_registry_schema_bytes_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Proposed Change

1. Cache the serialized default `ToolConfig` bytes after the built-in tool
   descriptors are declared.
2. For `built_in_tool_config(names=None)`, parse a fresh `ToolConfig` from the
   cached bytes so callers still receive an isolated mutable protobuf object.
3. Preserve the existing selected-name path by continuing to build a selected
   registry when `names` is provided.
4. Extend the existing registered `tool-registry-schema-bytes-cache` probe with
   a focused metric for repeated default `built_in_tool_config()` calls.

## Performance Probe

Probe ID: `tool-registry-schema-bytes-cache`

Added metric:

- `built_in_tool_config_elapsed_ms_mean` (lower is better)

The probe also records `built_in_tool_config_distinct_objects_mean` to verify
that each call still returns an isolated protobuf object rather than a shared
mutable singleton.

## Success Metrics

- Focused behavior tests pass.
- Changed-scope coverage is at least 95%.
- Local Linux registered probe shows a lower mean for repeated default
  `built_in_tool_config()` calls versus `origin/main`.

## Verification Commands

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_tool_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_tool_registry_schema_bytes_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_tool_registry_schema_bytes_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs`
- Changed-scope `coverage run` plus `scripts/changed_scope_coverage.py`.
- Registered probe command from `infra/perf/pr_scoped_probes.json` for
  `tool-registry-schema-bytes-cache`.
- `git diff --check`.
