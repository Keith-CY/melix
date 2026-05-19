# Tool config full-selection fast path

Date: 2026-05-19

## Scope

This performance slice optimizes only `built_in_tool_config()` in
`services/mlx-worker-python/worker/runtime/tool_registry.py`.

## Problem

The no-argument built-in tool config path already reuses a cached serialized
`ToolConfig` snapshot. Callers that explicitly pass the complete built-in tool
name list request the same full config, but the current path still rebuilds a
`ToolRegistry`, runs selection, and serializes a fresh worker tool config.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`tool-registry-schema-bytes-cache` in `infra/perf/pr_scoped_probes.json`. The
probe entry has focused `test_command`, `coverage_command`, and `probe_command`
entries for:

- `services/mlx-worker-python/worker/runtime/tool_registry.py`
- `services/mlx-worker-python/tests/test_tool_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/tool_registry_schema_bytes_probe.py`
- `infra/perf/pr_scoped_probes.json`

This slice extends that registered probe with explicit full-selection tool config
metrics so CI can validate the new hot path.

## Optimization slice

When `built_in_tool_config(names)` receives a clean full selection equal to
`BUILTIN_AGENTIC_TOOL_NAMES`, return a parsed copy of the cached serialized
snapshot, matching the existing `names is None` behavior.

The fast path is intentionally limited to clean full selections. Partial
selections, unknown names, blank trimming, and deduplication continue through the
existing registry selection path.

## Verification plan

- Run the registered focused pytest command locally on Linux.
- Run the registered changed-scope coverage command and require at least 95%
  changed-line coverage.
- Run `scripts/tool_registry_schema_bytes_probe.py` before and after the change
  and compare `full_selection_tool_config_elapsed_ms_mean`.
- Use GitHub Actions PR-scoped performance as the merge gate after pushing.

## Linux validation boundary

This slice is Python-only and locally verifiable on Linux. No Swift runtime
performance claims are made.
