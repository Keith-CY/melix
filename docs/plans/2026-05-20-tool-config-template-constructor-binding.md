# Tool config template constructor binding slice

## Scope

This Python-only performance slice targets repeated built-in tool config copies in
`services/mlx-worker-python/worker/runtime/tool_registry.py`.

The behavior remains unchanged: `built_in_tool_config(...)` still returns an
isolated protobuf `ToolConfig` instance for the default registry and for cached
selections. The optimization only binds the protobuf `ToolConfig` constructor at
module import time so the hot copy helper avoids a repeated nested module
attribute lookup before `CopyFrom(...)`.

## Registered probe

Affected path coverage is provided by the registered PR-scoped probe
`tool-registry-schema-bytes-cache` in `infra/perf/pr_scoped_probes.json`.
The entry already includes focused `test_command`, `coverage_command`, and
`probe_command` entries covering:

- `services/mlx-worker-python/worker/runtime/tool_registry.py`
- `services/mlx-worker-python/tests/test_tool_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/tool_registry_schema_bytes_probe.py`

## Verification plan

Run the registered focused tests, changed-scope coverage command, and registered
probe locally on Linux before opening the PR. The PR-scoped performance workflow
must select and complete the registered probe in CI before merge.

## Success criteria

- Focused tool registry tests pass.
- Changed-scope coverage for touched Python files remains at or above the
  repository threshold.
- The registered probe reports a lower or non-regressed
  `built_in_tool_config_elapsed_ms_mean` / related tool-config copy metrics.
- GitHub Actions and the PR-scoped performance workflow are green before merge.
