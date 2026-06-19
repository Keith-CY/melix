# Tool Registry OpenAI Tool Materialization Loop

## Scope

This Python-only performance slice touches only `ToolRegistry.as_openai_tools()` in `services/mlx-worker-python/worker/runtime/tool_registry.py`.

## Rationale

The registered `tool-registry-openai-tools-template-cache` probe repeatedly materializes OpenAI-compatible tool dictionaries from cached descriptor templates while verifying that returned payloads remain isolated from caller mutation. The current implementation already avoids descriptor re-entry, but the nested list/dict comprehension still creates a nested comprehension frame for every tool's schema properties.

## Implementation

- Keep the cached template shape and public payload structure unchanged.
- Replace the outer list comprehension and nested properties dict comprehension with explicit hot-loop construction.
- Bind `tools.append`, `dict.copy`, and `list.copy` once per call and build each properties dictionary directly.
- Preserve defensive copy isolation for schema property dictionaries and required-argument lists.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe `tool-registry-openai-tools-template-cache` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, changed-scope `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/tool_registry.py`
- `services/mlx-worker-python/tests/test_tool_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/tool_registry_openai_tools_probe.py`

## Validation

Local Linux validation for this slice must run the registered focused test command, changed-scope coverage command, and registered probe command before opening the PR. The probe's key metric is `elapsed_ms_mean`; `descriptor_as_openai_tool_calls_mean` must stay at `0.0` and `isolated_payload_calls_mean` must equal the requested iteration count.
