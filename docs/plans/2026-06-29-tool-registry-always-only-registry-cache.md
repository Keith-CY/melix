# Tool Registry Always-only Selection Registry Cache

## Slice

Cache the singleton always-only (`local_compute`) tool registry used by the
agentic tool selector's fallback/`max_selected_tools=1` path.

## Registered Probe

The changed path is already covered by the PR-scoped `tool-registry-select-name-index-cache`
probe in `infra/perf/pr_scoped_probes.json`:

- `test_command`: focused `test_tool_registry.py` and `test_pr_scoped_performance.py` coverage for tool selection behavior and probe selection.
- `coverage_command`: focused coverage over `worker.runtime.tool_registry` plus changed-scope coverage.
- `probe_command`: `scripts/tool_registry_select_probe.py`, which reports always-only, whitespace-turn, selector-planning, and selection-cache timing metrics.

No probe registry change is required for this slice.

## Behavior

No externally visible behavior changes. The fallback selection receipt remains
unchanged, but the singleton catalog path now reuses a cached selected registry
and metrics object instead of calling `ToolRegistry.select(("local_compute",))`
for every always-only selection.

## Validation Plan

1. Run focused behavior/probe-selection tests.
2. Run changed-scope coverage for `worker.runtime.tool_registry`.
3. Run the registered `tool_registry_select_probe.py` locally on Linux and compare
   with the baseline probe output captured before the change.
4. Use GitHub Actions PR-scoped performance as the merge gate.
