# PR-scoped scope matcher single-pass slice

## Scope

This Python-only performance slice targets the PR-scoped performance scope matcher in `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`.

## Registered probe

The affected path is covered by the existing registered PR-scoped performance probe `pr-scoped-performance-scope-matcher` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries, so this slice does not add a new probe.

## Change

Keep matching semantics unchanged while reducing per-scope matcher overhead:

- retain the exact-path fast path for exact-only registries;
- reuse the incoming changed-path set when available instead of rebuilding set membership state;
- intersect exact watch paths with the changed-path set so exact matching scales with exact hits rather than every changed path;
- bind hot-path lookups locally inside `_match_probe_indexes_uncached`.

2026-08-14 follow-up slice: `_matches_any_glob()` now also binds the glob-magic
predicate once before its watch-glob loop. This keeps exact-path and wildcard
semantics unchanged while avoiding repeated global lookups when command-summary
or legacy scope paths evaluate many watch globs. Because the adjacent
`pr-scoped-performance-registry-cache` probe watches the same production file,
its focused registry entry includes the existing `_matches_any_glob()` behavior
checks so changed-line coverage remains valid when both probes are selected.

## Verification plan

Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux before opening the PR. GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.

## Success criteria

- Focused behavior tests pass.
- Changed-scope coverage for the touched files is at least 95 percent.
- Local registered probe shows lower or non-regressing `build_scope_report_ms_mean` while preserving `selected_probe_count_mean` and `force_all_selected_mean`.
- PR-scoped performance CI selects and completes `pr-scoped-performance-scope-matcher` successfully before merge.
