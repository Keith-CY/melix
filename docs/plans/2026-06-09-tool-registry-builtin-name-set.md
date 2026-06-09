# Tool registry built-in name membership fast path

## Scope

This Python-only performance slice is limited to the agentic tool selection
membership check in `worker.runtime.tool_registry.select_agentic_tools_for_turn`.
It keeps tool selection behavior unchanged while avoiding repeated linear tuple
membership scans for built-in tool ids.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`.
That probe watches `services/mlx-worker-python/worker/runtime/tool_registry.py`,
`services/mlx-worker-python/tests/test_tool_registry.py`,
`services/mlx-worker-python/tests/test_pr_scoped_performance.py`, and
`scripts/tool_registry_select_probe.py`, and includes focused `test_command`,
`coverage_command`, and `probe_command` entries.

## Implementation plan

- Add a module-level frozenset snapshot for built-in agentic tool names.
- Use that set in the `add_tool` selection guard while preserving registry order
  through the existing tuple and selected-name list.
- Add a focused regression test proving unknown ids are still ignored and the
  set mirrors the canonical tuple.

## Verification plan

Run the registered focused tool-registry tests, changed-scope coverage, and the
registered select probe locally on Linux before pushing. GitHub Actions
PR-scoped performance remains the merge gate.
