# Tool Registry Preflight Name Set Cache

## Scope

This Python-only performance slice is limited to `worker.runtime.tool_registry` schema-consistency preflight name membership.

The schema-consistency preflight compares prompt-visible tool affordances against the selected callable registry and an optional catalog. The common path repeatedly needs membership checks for the same immutable registry name tuples. This slice caches a `frozenset` of each `ToolRegistry` instance's tool names during construction and reuses it in `preflight_agentic_tool_schema_consistency(...)` instead of rebuilding `set(...)` snapshots for every preflight call.

Behavior remains unchanged: receipt ordering still comes from `registry.names()` and `catalog.names()`, missing tools are still derived from referenced known tools that are absent from the selected callable registry, and invalid affordances remain counted without raw text leakage.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe `tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`. This slice extends the existing probe script and registry metrics with:

- `schema_consistency_preflight_elapsed_ms_mean`
- `schema_consistency_missing_tools_mean`

The same registry entry already includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/tool_registry.py`
- `services/mlx-worker-python/tests/test_tool_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/tool_registry_select_probe.py`

## Verification Plan

Run the registered focused tests, changed-scope coverage command, `git diff --check`, and the registered `tool-registry-select-name-index-cache` probe locally on Linux before opening the PR. GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.
