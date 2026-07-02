# Tool registry worker config full-selection fast path

## Scope

This Python-only performance slice is limited to
`services/mlx-worker-python/worker/runtime/tool_registry.py`, specifically the
built-in worker `ToolConfig` copy path used by `built_in_tool_config()`.

## Probe registration

The affected path is covered by the registered PR-scoped probe
`tool-registry-schema-bytes-cache` in `infra/perf/pr_scoped_probes.json`. The
probe includes focused `test_command`, `coverage_command`, and `probe_command`
entries and tracks `full_selection_tool_config_elapsed_ms_mean` alongside the
existing schema and partial-selection metrics.

## Change

When callers pass the canonical full built-in tool tuple, return an isolated copy
of the already-built full template immediately. This preserves protobuf object
isolation while avoiding the selection-cache dictionary lookup on the hot full
selection path. The slice also binds the copy helper locally inside
`built_in_tool_config()` so all return branches reuse the same fast local lookup.

## Follow-up slice: worker config template copy

A 2026-06-28 follow-up keeps the same protobuf isolation contract for
`ToolRegistry.as_worker_tool_config()` but caches the built `ToolConfig` object as
an internal template. Repeated calls now copy the cached template directly instead
of reparsing the cached serialized bytes. The method still returns a fresh
protobuf object every time, so caller mutations cannot affect later callers or the
registry cache.

## Verification plan

- Focused tool-registry tests, including full tuple selection copy isolation and
  direct `ToolRegistry.as_worker_tool_config()` copy isolation.
- Registered changed-scope coverage for the tool-registry probe scope.
- Registered local probe on Linux, comparing the pre-change and post-change
  `full_selection_tool_config_elapsed_ms_mean`,
  `partial_selection_tool_config_elapsed_ms_mean`, and adjacent metrics.

## Boundary

This is a Python worker slice and is fully locally verifiable on Linux. No Swift
runtime effect is claimed.
