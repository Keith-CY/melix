# Tool selection hot-path allocation performance slice

## Scope

Optimize the Python agentic tool-selection hot path by avoiding repeated metrics
snapshot lookups in the receipt builder and replacing the whitespace-only keyword
check's `strip()` allocation with `isspace()`. The behavior remains unchanged:
selected tool ordering, selection sources, schema byte counts, keyword matching,
and fallback metadata must match the existing contract.

## Registered probe

The affected path is already covered by the PR-scoped registered probe
`tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`.
That probe watches `services/mlx-worker-python/worker/runtime/tool_registry.py`,
includes focused `test_command`, `coverage_command`, and `probe_command` entries,
and measures selector planning latency plus selected schema byte metrics.

## Implementation plan

1. Add a focused regression test proving `_build_tool_selection_result()` reads
   the full and selected registry metrics snapshots once each.
2. Bind `registry.metrics()` and `selected_registry.metrics()` to local variables
   inside `_build_tool_selection_result()` and reuse them for receipt fields.
3. Replace the keyword matcher's whitespace-only guard with `str.isspace()` to
   avoid building a stripped copy on the cached hot path.
4. Run the registered focused tests, changed-scope coverage, and the registered
   probe locally on Linux. Use the PR-scoped performance workflow as the CI
   validation source after push.

## Success criteria

- Focused tool-registry tests pass.
- Changed-scope coverage for the touched files is at least 95%.
- The registered probe shows a non-regressing selector-planning metric.
