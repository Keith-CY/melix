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

## Follow-up Slice: Slotted Descriptor Snapshots

The 2026-05-19 follow-up keeps the tool registry API and copy-on-return schema
payload behavior unchanged, but marks the small immutable dataclass snapshots as
slotted: `ToolArgumentDescriptor`, `ToolDescriptor`, and `ToolRegistryMetrics`.
These objects are read repeatedly by the registered tool-registry probes and do
not need per-instance `__dict__` storage. The same slice also caches serialized
built-in tool configs for normalized partial selections so repeated
`built_in_tool_config((...))` calls avoid re-entering registry selection while
still returning fresh mutable protobuf objects.

Expected effect:

- reduce per-descriptor memory overhead;
- improve repeated partial-selection `built_in_tool_config((...))` calls by
  reusing cached serialized protobuf bytes;
- keep `schema_payload_elapsed_ms_mean`, `elapsed_ms_mean`, and adjacent
  tool-registry probe timings neutral-to-improved;
- preserve mutation isolation for returned schema payload dictionaries and
  protobuf configs.

## Follow-up Slice: Cached Required-Argument List Copy

The 2026-05-20 follow-up keeps the same `ToolDescriptor.schema_payload()` API
and copy-on-return behavior, but stores the required argument snapshot in both
tuple and list form during descriptor initialization. `required_arguments`
continues to expose the immutable tuple, while `schema_payload()` can copy the
prebuilt list directly instead of rebuilding a list from the tuple on every
call.

Expected effect:

- reduce repeated schema payload construction overhead measured by
  `schema_payload_elapsed_ms_mean`;
- keep returned schema payloads independently mutable;
- leave registry selection, protobuf config serialization, and tool definitions
  unchanged.

## Follow-up Slice: OpenAI Tool Copy Local Bindings

The 2026-05-23 follow-up keeps the `ToolRegistry.as_openai_tools()` API and
copy-on-return behavior unchanged, but binds `dict.copy` and `list.copy` once
per call before cloning cached OpenAI tool schema templates. The returned tool
payloads remain independently mutable, while the inner hot loop avoids repeated
method-attribute lookups for every schema property and required-argument list.

Expected effect:

- reduce repeated OpenAI tool payload construction overhead measured by
  `tool-registry-openai-tools-template-cache` `elapsed_ms_mean`;
- preserve mutation isolation for returned `parameters.properties` dictionaries
  and `parameters.required` lists;
- leave registry selection, schema payload construction, and protobuf config
  serialization unchanged.

## Follow-up Slice: Schema Payload Copy Function Bindings

The 2026-05-26 follow-up keeps the `ToolDescriptor.schema_payload()` API and
copy-on-return behavior unchanged, but reuses the module-level `dict.copy` and
`list.copy` bindings inside the schema-payload constructor. This mirrors the
already-applied OpenAI tool payload slice and removes repeated bound-method
lookups for every schema dictionary and required-argument list copied during the
registered schema-payload probe.

Expected effect:

- reduce repeated schema payload construction overhead measured by
  `tool-registry-schema-bytes-cache` `schema_payload_elapsed_ms_mean`;
- preserve independently mutable returned `properties` dictionaries and
  `required` lists;
- leave tool selection, OpenAI tool payload construction, and protobuf config
  serialization unchanged.

## Validation Plan

1. Run the registered focused test command locally on Linux.
2. Run the registered changed-scope coverage command locally and require at
   least 95% coverage for touched scope.
3. Run the registered probe command locally before and after the slice and
   compare the relevant registered metric (`schema_payload_elapsed_ms_mean` for
   schema-payload slices, or `elapsed_ms_mean` for the OpenAI tool payload slice)
   over repeated samples.
4. Push only if local evidence is neutral-to-improved and rely on the GitHub
   PR-scoped performance workflow as the merge gate.
