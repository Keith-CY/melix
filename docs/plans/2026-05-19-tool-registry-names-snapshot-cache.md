# Tool Registry Names Snapshot Cache

## Goal

Reduce repeated tuple allocation in `worker.runtime.tool_registry.ToolRegistry.names()` for agentic tool configuration paths that query registry names repeatedly during request setup or probe selection.

## Scope

This slice is intentionally limited to the Python tool registry name snapshot path:

- cache the ordered tool-name tuple once during `ToolRegistry` construction;
- return that immutable snapshot from `names()`;
- add a registered PR-scoped performance probe for repeated `names()` calls.

It does not change tool descriptors, schema serialization, selection semantics, worker protobuf exports, or built-in tool definitions.

## Performance Probe

Registered probe: `tool-registry-names-snapshot-cache` in `infra/perf/pr_scoped_probes.json`.

The probe runs `scripts/tool_registry_names_probe.py`, repeatedly calls `ToolRegistry.names()`, asserts the stable built-in ordering, and reports:

- `elapsed_ms_mean` (`lower_is_better`)
- `same_names_object_calls_mean` (`higher_is_better`)

## Verification Plan

Run the focused registry tests, changed-scope coverage command, and the registered probe locally on Linux before opening the PR. CI remains the source of truth for the PR-scoped base-vs-head performance report.
