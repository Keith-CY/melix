# Tool Registry Schema Payload Local Bindings

## Scope

This Python performance slice is limited to the agentic tool registry schema
payload hot path in `services/mlx-worker-python/worker/runtime/tool_registry.py`.
It does not change tool registry behavior, protobuf schemas, dependencies, or
runtime observability.

## Optimization Hypothesis

`ToolDescriptor.schema_payload()` is exercised repeatedly by the registered tool
registry probe while constructing OpenAI tool schemas and measuring schema
payload overhead. Binding the cached schema-property tuple and required argument
tuple to locals before constructing the returned payload should reduce attribute
and property lookup overhead while preserving the existing copy-on-return
semantics for nested schema dictionaries and required argument lists.

## Registered Probe

The affected path is already covered by the registered PR-scoped probe
`tool-registry-schema-bytes-cache` in `infra/perf/pr_scoped_probes.json`. The
entry includes focused `test_command`, `coverage_command`, and `probe_command`
commands and reports `schema_payload_elapsed_ms_mean` as the primary metric for
this slice. The same watch glob also triggers adjacent tool registry registered
probes in CI.

## Validation Plan

1. Run the registered focused test command locally on Linux.
2. Run the registered changed-scope coverage command locally and require at
   least 95% coverage for touched scope.
3. Run the registered probe command locally before and after the slice and
   compare `schema_payload_elapsed_ms_mean` over repeated samples.
4. Push only if local evidence is neutral-to-improved and rely on the GitHub
   PR-scoped performance workflow as the merge gate.
