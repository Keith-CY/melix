# Tool Config Full-List Template Cache

## Goal

Reduce repeated allocation in `worker.runtime.tool_registry.built_in_tool_config()` when callers pass an exact ordered list containing every built-in agentic tool name. The previous path converted that list to a tuple before discovering that the full built-in config template was already cached.

## Scope

This Python-only performance slice is limited to the built-in tool config selection fast path:

- cache a private list-form snapshot of `BUILTIN_AGENTIC_TOOL_NAMES` next to the existing tuple snapshot;
- return an isolated copy of the full built-in `ToolConfig` template when `names` equals that list snapshot;
- avoid tuple conversion for exact full-list callers;
- preserve the existing tuple cache, partial-selection cache, isolated-copy behavior, unknown-name validation, and selection ordering semantics;
- extend the registered tool-registry select probe with separate full-list
  `built_in_tool_config()` workload metrics without folding that workload into
  the existing selection elapsed metric.
- remove per-instance `ToolRegistry` dictionaries so cached registry and
  selection objects have lower steady-state attribute and allocation overhead.

It does not change tool descriptor definitions, protobuf schemas, generated outputs, parser contracts, or non-exact partial-selection behavior.

## Performance Probe

Registered probe: `tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`.

The probe runs `scripts/tool_registry_select_probe.py`, mixing cached partial tuple selections and exact full-list `ToolRegistry.select()` calls in the original `elapsed_ms_mean` workload. It measures exact full-list `built_in_tool_config()` calls in a separate timed loop so the selection metric remains comparable with historical base runs. It reports:

- `elapsed_ms_mean` (`lower_is_better`)
- `select_calls_mean` (`informational`)
- `full_list_self_hits_mean` (`higher_is_better`)
- `full_config_template_hits_mean` (`higher_is_better`)
- `full_config_template_elapsed_ms_mean` (`lower_is_better`)

## Verification Plan

Run the focused registry tests, changed-scope coverage command, and the registered probe locally on Linux before opening the PR. CI remains the source of truth for the PR-scoped base-vs-head performance report.
