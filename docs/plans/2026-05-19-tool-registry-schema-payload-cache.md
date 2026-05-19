# Tool Registry Schema Payload Cache Performance Slice

## Scope

This Python-only performance slice targets `ToolDescriptor.schema_payload()` in
`services/mlx-worker-python/worker/runtime/tool_registry.py`. The method is used
when exporting agentic tool definitions to OpenAI-compatible payloads and is also
covered by the existing schema-byte-count registered probe workload.

## Registered probe

The affected path is already covered by the registered PR-scoped performance
probe `tool-registry-schema-bytes-cache` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/tool_registry.py`
- `services/mlx-worker-python/tests/test_tool_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/tool_registry_schema_bytes_probe.py`

## Optimization hypothesis

`schema_payload()` currently rebuilds every argument schema by calling
`ToolArgumentDescriptor.json_schema()` for each export. Tool descriptors are
immutable after construction, so the normalized argument schema dictionaries can
be cached at descriptor construction time. Each call should still return fresh
mutable dictionaries to preserve caller isolation, but it can avoid repeated
method dispatch and field lookup while constructing the payload.

## Verification plan

1. Add focused tests proving `schema_payload()` reuses the cached argument schema
   snapshot and still returns isolated mutable payload dictionaries.
2. Implement only the descriptor-level cached argument schema tuple.
3. Run the registered focused pytest command and changed-scope coverage command
   locally on Linux.
4. Run the registered `tool-registry-schema-bytes-cache` probe locally on Linux
   before and after the change and compare `schema_payload_elapsed_ms_mean`.
5. Use PR-scoped performance CI as the final registered probe gate before merge.

## Success criteria

- Focused tests pass and changed-scope coverage remains at or above 95%.
- Registered local probe shows a clear improvement in
  `schema_payload_elapsed_ms_mean` without changing schema bytes or required
  argument behavior.
- GitHub Actions and the PR-scoped performance workflow are green before merge.
