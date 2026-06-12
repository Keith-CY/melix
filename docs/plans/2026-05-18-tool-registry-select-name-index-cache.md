# Tool Registry Select Name Index Cache

Date: 2026-05-18

## Scope

This performance slice optimizes `ToolRegistry.select()` in
`services/mlx-worker-python/worker/runtime/tool_registry.py` only.

## Problem

The agentic tool registry contract requires selection requests to preserve the
requested order, deduplicate repeated names, and reject unknown tool names before
execution. The current select path rebuilds a `name -> descriptor` dictionary and
an additional set for every selection call even though the registry descriptor
set is immutable for the lifetime of a `ToolRegistry` instance.

## Plan

- Add a registry-local cached tool-name index after duplicate-name validation.
- Keep duplicate-name validation in `_validate()` so malformed registries still
  fail with the existing error.
- Update tests to prove `select()` uses the cached index while preserving order,
  deduplication, and unknown-name errors.
- Register a focused PR-scoped performance probe for repeated registry selection.

## Performance Probe

Registered PR-scoped probe: `tool-registry-select-name-index-cache` in
`infra/perf/pr_scoped_probes.json`.

Focused commands:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_tool_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_tool_registry_schema_bytes_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_tool_registry_select_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_tool_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_tool_registry_schema_bytes_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_tool_registry_select_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/tool_registry.py services/mlx-worker-python/tests/test_tool_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/tool_registry_select_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/tool_registry_select_probe.py
```

## Slice update: selected-registry cache

The next incremental slice keeps the same `tool-registry-select-name-index-cache`
registered probe and narrows the optimization to repeated `ToolRegistry.select()`
calls with the same normalized requested-name tuple. The registry now caches the
constructed selected `ToolRegistry` per tuple after unknown-name validation,
so hot selection loops avoid rebuilding the selected registry, its name index,
and its aggregate metrics snapshot. Selection order, whitespace normalization,
deduplication, and unknown-name errors remain unchanged.

## Slice update: single-pass selection normalization

This incremental slice still uses the `tool-registry-select-name-index-cache`
registered probe and narrows the hot path before cache lookup. `ToolRegistry.select()`
now normalizes, drops blanks, and deduplicates requested names in one explicit
pass instead of building a generator and a temporary insertion-ordered dictionary.
When the normalized requested-name tuple already matches the immutable registry
name tuple, the method returns the current registry instead of constructing and
caching an equivalent selected registry. The registry also keeps a bounded
selected-registry cache so repeated ad hoc selections retain the hot cache
benefit without unbounded growth. Selection order, whitespace normalization,
deduplication, and unknown-name errors remain unchanged.

## Slice update: always-only routing cap fast path

This incremental slice keeps the same `tool-registry-select-name-index-cache`
registered probe and narrows the optimization to agentic tool routing requests
where the always-available tool set already fills `max_selected_tools`. In that
case, optional vector iteration and keyword/context scans cannot add another
tool, so `select_agentic_tools_for_turn()` now returns the always-only selection
immediately while preserving the fallback receipt shape. The shared receipt
builder is kept as a module-level helper so the existing vector/keyword paths do
not pay a per-call nested-function allocation cost. The probe records a separate
`always_only_planning_elapsed_ms_mean` metric for this bounded-cap routing path.

## Acceptance Criteria

- Focused behavior tests pass locally on Linux.
- Changed-scope coverage is at least 95%.
- The registered probe shows a directionally lower repeated-selection elapsed
  time on head compared with the base implementation.
- CI PR-scoped performance completes successfully before merge.
