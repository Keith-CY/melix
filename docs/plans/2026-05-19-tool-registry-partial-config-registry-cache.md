# Tool registry partial config registry cache

## Scope

This Python-only performance slice is limited to partial-selection calls through
`built_in_tool_config()` in
`services/mlx-worker-python/worker/runtime/tool_registry.py`.

## Probe

The affected path is already covered by the registered PR-scoped probe
`tool-registry-schema-bytes-cache` in `infra/perf/pr_scoped_probes.json`. This
slice extends the probe script to report
`partial_selection_tool_config_elapsed_ms_mean` while keeping the existing
focused `test_command`, `coverage_command`, and `probe_command` entries.

## Implementation plan

- Reuse a module-local built-in `ToolRegistry` for partial built-in tool config
  selection instead of constructing a fresh registry for every call.
- Preserve the existing defensive `ToolConfig` copy behavior for callers.
- Add a regression test proving partial `built_in_tool_config()` no longer routes
  through the public `built_in_tool_registry()` constructor path.

## Verification

Run the registered focused tests, changed-scope coverage command, and the
registered PR-scoped performance probe locally on Linux. Use PR-scoped
performance CI as the final base-vs-head validation source before merge.
