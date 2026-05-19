# Tool registry raw tuple cache alias

## Summary

This Python-only performance slice keeps `ToolRegistry.select()` behavior
unchanged while caching a validated raw tuple request as an alias to the
normalized selection result. The registered select probe repeatedly sends a
small set of tuple selections, including a duplicate-name tuple, so the current
implementation still re-normalizes that duplicate tuple on every call even after
its normalized selected registry is cached.

## Registered PR-scoped probe

The affected path is already covered by the registered PR-scoped performance
probe `tool-registry-select-name-index-cache` in
`infra/perf/pr_scoped_probes.json`. The probe entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/tool_registry.py`
- `services/mlx-worker-python/tests/test_tool_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/tool_registry_select_probe.py`

No new probe registry entry is required for this slice.

## Optimization slice

After `select()` strips, filters, deduplicates, validates, and builds or reuses
the normalized selection, store the original tuple request as an additional
cache key when it differs from the normalized tuple. Future identical tuple
requests can use the existing tuple cache fast path before repeating the
normalization loop. List inputs remain uncached by raw identity and still follow
the existing normalization path.

The cache remains bounded by the existing selection-cache limit and cache-clear
behavior. Missing-name errors, blank-name filtering, deduplication order, and
complete-selection self returns are unchanged.

## Verification plan

- Run the focused tool-registry tests locally on Linux.
- Run the registered changed-scope coverage command and require at least 95%
  changed-line coverage.
- Run `scripts/tool_registry_select_probe.py` before and after the change and
  compare `elapsed_ms_mean` while preserving `select_calls_mean` and checksum.
- Use GitHub Actions PR-scoped performance as the merge gate after pushing.

## Linux validation boundary

This slice is entirely Python and locally verifiable on Linux. No Swift runtime
performance claims are made.
