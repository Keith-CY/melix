# PR-scoped Probe Match Exact Lookup Loop

## Goal

Reduce transient allocation in PR-scoped performance probe selection when changed
paths are matched against registered probe `watch_globs`.

## Scope

This slice is Python-only and locally verifiable on Linux. It changes only the
exact-path matching step in `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`.
Wildcard glob matching, prefix pruning, cache keys, and selected-probe semantics
stay unchanged.

## Registered Performance Probe

Use the existing `pr-scoped-performance-registry-cache` probe in
`infra/perf/pr_scoped_probes.json`. The affected source path is already covered
by the probe and the registry entry provides focused `test_command`,
`coverage_command`, and `probe_command` entries.

## Implementation Plan

1. Keep `_probe_match_indexes(...)` as the cached source of exact and wildcard
   match indexes.
2. Replace the temporary `frozenset(changed_paths)` plus dictionary-key
   intersection with a direct changed-path loop and exact dictionary lookup.
3. Preserve the existing wildcard loop and cache behavior.
4. Run the registered focused tests, changed-scope coverage, and local registered
   probe on Linux before opening the PR. The PR-scoped performance workflow is
   the merge gate for the registered CI probe result.

## Success Metrics

- Focused behavior tests pass.
- Changed-scope coverage for touched files remains at least 95%.
- Registered probe shows stable or improved `build_scope_report_ms_mean` and no
  regression in registry load metrics against `origin/main`.
