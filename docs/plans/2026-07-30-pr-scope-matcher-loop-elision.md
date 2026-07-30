# PR-scoped scope matcher wildcard loop elision

## Slice

This Python-only performance slice is limited to `_match_probe_indexes_uncached(...)` in `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe `pr-scoped-performance-scope-matcher` in `infra/perf/pr_scoped_probes.json`. The registry entry already provides focused `test_command`, `coverage_command`, and `probe_command` entries for the scope matcher code and tests.

## Optimization hypothesis

The wildcard matching loop currently builds a two-item tuple of matcher groups for every changed path before iterating unbucketed and bucketed wildcard matchers, and performs repeated bound-method lookup for `path.startswith`. Splitting the two loops and binding `path.startswith` once per path keeps exact matching order and selected probe semantics unchanged while removing per-path tuple allocation and repeated attribute lookup in large changed-file sets.

## Validation plan

1. Run the registered focused test command for `pr-scoped-performance-scope-matcher` locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux.
3. Run the registered probe locally on Linux before and after the change and compare `build_scope_report_ms_mean`, `selected_probe_count_mean`, `force_all_selected_mean`, and `command_summary_ms_mean`.
4. Use GitHub Actions PR-scoped performance as the final registered probe validation and merge gate.

## Acceptance

Accept only if behavior tests pass, changed-scope coverage remains at or above 95%, selected probe and force-all counters remain unchanged, and the registered probe does not show an in-scope regression.
