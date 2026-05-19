# Tool Registry Select Full-List Fast Path

## Goal

Reduce repeated normalization work in `worker.runtime.tool_registry.ToolRegistry.select()` when callers pass an exact ordered list containing the complete built-in tool registry. This path appears in agentic tool configuration setup where JSON-derived lists may already match the registry order.

## Scope

This slice is intentionally limited to the Python tool registry selection path:

- cache a private list-form name snapshot beside the existing immutable tuple snapshot;
- detect exact full-list selections before trimming and deduplicating requested names;
- return the current registry instance for that exact list, matching the existing complete-selection semantics;
- keep whitespace trimming, duplicate removal, unknown-name errors, and partial-selection cache behavior unchanged;
- extend the registered select probe to include the exact full-list workload.

It does not change tool descriptors, schema serialization, worker protobuf exports, built-in tool definitions, or non-exact selection normalization.

## Performance Probe

Registered probe: `tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`.

The probe runs `scripts/tool_registry_select_probe.py`, mixes cached partial tuple selections with exact full-list selections, and reports:

- `elapsed_ms_mean` (`lower_is_better`)
- `select_calls_mean` (`informational`)
- `full_list_self_hits_mean` (`higher_is_better`)

## Verification Plan

Run the focused registry tests, changed-scope coverage command, and the registered probe locally on Linux before opening the PR. CI remains the source of truth for the PR-scoped base-vs-head performance report.
