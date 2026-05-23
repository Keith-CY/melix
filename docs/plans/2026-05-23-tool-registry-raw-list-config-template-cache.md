# Tool registry raw list config template cache

## Scope

This Python performance slice is limited to `worker.runtime.tool_registry.built_in_tool_config()` when callers pass a partial built-in tool selection as a mutable list whose raw values need normalization, such as whitespace trimming or duplicate removal.

The slice does not change the exported built-in tool registry contract, protobuf schemas, parser metadata, tool ordering semantics, or copy-on-return isolation behavior.

## Registered probe

The affected code path is covered by the existing registered PR-scoped probe `tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`.

This slice extends `scripts/tool_registry_select_probe.py` with raw partial config-template metrics so CI and local runs can verify that normalized raw-list selections reuse cached serialized `ToolConfig` templates after the first normalization pass:

- `raw_partial_config_template_elapsed_ms_mean` (lower is better)
- `raw_partial_config_template_hits_mean` (higher is better)

## Implementation plan

1. Add a regression test proving repeated raw-list partial selections skip `ToolRegistry.select()` after the first `built_in_tool_config()` call.
2. Store the serialized selected `ToolConfig` template under both normalized names and the raw requested tuple when normalization changes the key.
3. Extend the registered probe output and registry metrics for the raw partial config-template path.
4. Run focused tests, changed-scope coverage, and the registered probe locally on Linux before opening the PR.

## Validation boundary

This is a Python-only slice and is locally verifiable on Linux. Swift runtime effects are not involved.
