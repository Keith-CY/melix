# Tool registry built-in singleton

## Scope

This Python-only performance slice is limited to repeated calls through
`built_in_tool_registry()` in
`services/mlx-worker-python/worker/runtime/tool_registry.py`.

## Probe

The affected path is covered by the registered PR-scoped probe
`tool-registry-names-snapshot-cache` in `infra/perf/pr_scoped_probes.json`.
This slice extends the probe with `registry_factory_elapsed_ms_mean` so the
registered probe directly measures repeated `built_in_tool_registry()` access in
addition to repeated `ToolRegistry.names()` access. The probe keeps focused
`test_command`, `coverage_command`, and `probe_command` entries and remains
Linux-runnable.

## Implementation plan

- Return the existing module-local built-in registry singleton from
  `built_in_tool_registry()` instead of constructing a new `ToolRegistry` on
  every call.
- Preserve defensive `ToolConfig` copy behavior in `built_in_tool_config()`.
- Add a regression test proving repeated built-in registry access reuses the
  singleton registry while preserving the exported contract.

## Verification

Run the registered focused tests, changed-scope coverage command, and the
registered PR-scoped performance probe locally on Linux. Use PR-scoped
performance CI as the final base-vs-head validation source before merge.
