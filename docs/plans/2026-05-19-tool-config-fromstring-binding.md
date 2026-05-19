# Tool config FromString binding

Date: 2026-05-19

## Scope

This performance slice optimizes only `built_in_tool_config()` and
`ToolRegistry.as_worker_tool_config()` in
`services/mlx-worker-python/worker/runtime/tool_registry.py`.

## Problem

The cached tool-config paths already avoid rebuilding descriptor schemas and
registry selections, but each hot call still resolves
`common_pb2.ToolConfig.FromString` through the protobuf module and message class
before parsing the cached serialized `ToolConfig` bytes. These cached-byte paths
are exercised frequently when agentic tool metadata is attached to generation
requests.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`tool-registry-schema-bytes-cache` in `infra/perf/pr_scoped_probes.json`. The
entry includes focused `test_command`, `coverage_command`, and `probe_command`
entries for:

- `services/mlx-worker-python/worker/runtime/tool_registry.py`
- `services/mlx-worker-python/tests/test_tool_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/tool_registry_schema_bytes_probe.py`
- `infra/perf/pr_scoped_probes.json`

No registry change is required for this slice.

## Optimization slice

Bind `common_pb2.ToolConfig.FromString` once at module import and use that local
binding for cached serialized tool-config parses. This keeps message mutability
semantics unchanged because every call still returns a freshly parsed protobuf
message.

## Verification plan

- Run the registered focused pytest command locally on Linux.
- Run the registered changed-scope coverage command and require at least 95%
  changed-line coverage.
- Run `scripts/tool_registry_schema_bytes_probe.py` before and after the change
  and compare cached tool-config metrics.
- Use GitHub Actions PR-scoped performance as the merge gate after pushing.

## Linux validation boundary

This slice is Python-only and locally verifiable on Linux. No Swift runtime
performance claims are made.
