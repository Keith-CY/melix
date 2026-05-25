# Tool Registry OpenAI Tool Append Binding Slice

## Scope

This Python performance slice is limited to `ToolRegistry.as_openai_tools()` in
`services/mlx-worker-python/worker/runtime/tool_registry.py`.

The method is on the agentic tool-config hot path and constructs isolated
OpenAI function-tool payloads repeatedly. The slice keeps payload semantics and
mutation isolation unchanged while binding the result list append method once
outside the per-tool loop.

## Registered Probe

The affected path is already covered by the registered PR-scoped performance
probe `tool-registry-openai-tools-template-cache` in
`infra/perf/pr_scoped_probes.json`.

The probe provides:

- focused pytest coverage for `test_tool_registry.py` and probe dispatch tests;
- changed-scope coverage for `tool_registry.py`, `test_tool_registry.py`,
  `test_pr_scoped_performance.py`, and `scripts/tool_registry_openai_tools_probe.py`;
- a command-json performance probe that repeatedly calls
  `ToolRegistry.as_openai_tools()`, verifies descriptor conversion is not
  re-entered, and checks returned payloads remain mutation-isolated.

## Verification Plan

1. Run the registered focused tests locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux.
3. Run `scripts/tool_registry_openai_tools_probe.py` before and after the change
   and compare `elapsed_ms_mean` while confirming unchanged descriptor and
   isolation metrics.
4. Use the hosted PR-scoped performance workflow as the merge gate.

## Expected Behavior

- `as_openai_tools()` continues returning fresh nested payloads so callers can
  mutate returned `required` lists without polluting later calls.
- `descriptor_as_openai_tool_calls_mean` remains `0.0` because the registry uses
  cached templates instead of invoking descriptor conversion for every call.
- Performance should be neutral-to-better by avoiding repeated `tools.append`
  method lookup inside the loop.
