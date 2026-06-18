# 2026-06-18 PR Scope Exact Glob Membership

## Context

The PR-scoped performance scope builder checks changed paths against each probe's
`watch_globs` while preparing coverage paths and probe selection. Most probe
registrations include exact repository-relative paths for production files, test
files, probe scripts, and registry entries. Exact-path hits currently still enter
the generic glob helper loop before returning.

## Slice

Keep this optimization limited to `_matches_any_glob(...)` in
`services/mlx-worker-python/worker/productization/pr_scoped_performance.py`.
Add a direct tuple-membership hit before the generic helper loop so exact changed
paths avoid repeated helper dispatch and glob-magic checks. Preserve wildcard
semantics by retaining the existing helper loop for misses and wildcard entries.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`pr-scoped-performance-scope-matcher` in `infra/perf/pr_scoped_probes.json`.
That registry entry watches the implementation file, focused PR-scoped
performance tests, and the registry itself, and includes focused
`test_command`, `coverage_command`, and `probe_command` entries.

## Verification Plan

1. Add a regression test proving exact `_matches_any_glob` hits bypass helper
   dispatch while wildcard fallback remains covered by existing tests.
2. Run the registered focused test command locally on Linux.
3. Run changed-scope coverage for the touched implementation and test files.
4. Run the registered PR-scoped performance probe locally on Linux and compare
   against `origin/main`.
5. Use GitHub Actions, including the PR-scoped performance workflow, as the
   final merge gate.

## Success Criteria

- Focused tests pass.
- Changed-scope coverage remains at or above 95%.
- The registered scope-matcher probe shows a non-regressing or improved
  `build_scope_report_ms_mean` without changing selected probe counts.
- CI completes successfully before merge.
