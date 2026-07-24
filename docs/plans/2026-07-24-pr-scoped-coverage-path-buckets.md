# PR-scoped coverage path wildcard bucket reuse

## Scope

This Python-only performance slice is limited to `coverage_paths_by_probe_id()` in the PR-scoped performance selector. The selector already builds top-level wildcard matcher buckets for probe selection; this slice reuses those same buckets while computing per-probe `coverage_paths` so large PRs do not rescan every wildcard matcher for every changed path.

## Probe coverage

The affected path is covered by the registered `pr-scoped-performance-scope-matcher` probe in `infra/perf/pr_scoped_probes.json`. That registry entry includes focused `test_command`, `coverage_command`, and `probe_command` fields and watches:

- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

This slice extends the focused test list with `test_coverage_paths_by_probe_id_buckets_wildcard_matchers` so the coverage path helper proves it consults only the matching top-level wildcard bucket.

## Implementation plan

1. Add a regression test proving coverage path matching does not scan wildcard buckets from unrelated top-level prefixes.
2. Reuse `_probe_match_indexes()` bucket output in `_coverage_paths_by_probe_id()` and keep exact-path/context-only semantics unchanged.
3. Run focused pytest, the changed-scope coverage command, `git diff --check`, and the registered local probe on Linux.
4. Use GitHub Actions PR-scoped performance as the final merge gate.

## Success metrics

- Focused PR-scoped performance tests pass.
- Changed-scope coverage remains at 100% for the touched lines/files.
- Local registered probe reports lower `build_scope_report_ms_mean` for head versus the same-worktree baseline run, with unchanged selected probe and force-all counts.
