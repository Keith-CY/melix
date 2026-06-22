# PR-scoped exact glob single-pass slice

## Scope

This Python-only performance slice is limited to `worker.productization.pr_scoped_performance._matches_any_glob()` and the registered `pr-scoped-performance-scope-matcher` probe.

## Registered probe

The affected path is already covered by `infra/perf/pr_scoped_probes.json` entry `pr-scoped-performance-scope-matcher`, with focused `test_command`, `coverage_command`, and `probe_command` entries. This slice extends the focused test selection with a regression guard for exact non-matching watch globs.

## Change

`_matches_any_glob()` now handles exact watch-glob hits and exact misses inside the main loop. Exact misses skip `_glob_matches_path()`, avoiding redundant magic/prefix handling before the function reaches wildcard entries.

## Verification plan

1. Run the registered focused test and coverage commands locally on Linux.
2. Run the registered `pr-scoped-performance-scope-matcher` probe against `origin/main` and the branch worktree.
3. Use GitHub Actions PR-scoped performance as the merge gate.

## Evidence

To be filled in the PR body after local verification and CI.
