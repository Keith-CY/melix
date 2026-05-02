# PR-scoped Performance Force-all Matcher Loop Optimization

## Goal

Reduce per-path overhead in the PR-scoped performance scope matcher by replacing the force-all compiled-glob helper's generator expression with an explicit loop. This keeps matching semantics unchanged while avoiding generator allocation in a helper that runs for every changed path during scope selection.

## Scope

- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- This plan document

No probe registry change is required: the affected path is already covered by the registered `pr-scoped-performance-scope-matcher` probe in `infra/perf/pr_scoped_probes.json`, which declares focused `test_command`, `coverage_command`, and `probe_command` entries.

## Verification Plan

Run the registered probe commands locally on Linux:

1. Focused pytest from the `pr-scoped-performance-scope-matcher` registry entry.
2. Changed-scope coverage from the same registry entry.
3. Registered probe comparison via `scripts/pr_scoped_performance_run.py --probe-id pr-scoped-performance-scope-matcher` against an `origin/main` baseline worktree.

CI remains the merge gate for the PR-scoped performance report before merge.

## Expected Metrics

The probe reports:

- `build_scope_report_ms_mean` lower is better.
- `selected_probe_count_mean` unchanged.
- `force_all_selected_mean` unchanged.

The slice is accepted only if behavior tests pass and the registered probe shows a stable local improvement or no semantic metric drift with CI validation.
