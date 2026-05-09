# PR-scoped Performance Empty Direct Path Fast Path

## Goal

Avoid scanning every registered probe watch glob when a PR-scoped performance scope request has no direct changed paths to match. This happens for empty diffs and for context-only inputs after force/context filtering.

## Registered probe coverage

The affected path is already covered by the registered `pr-scoped-performance-scope-matcher` PR-scoped performance probe in `infra/perf/pr_scoped_probes.json`. The probe provides focused `test_command`, `coverage_command`, and `probe_command` entries for `services/mlx-worker-python/worker/productization/pr_scoped_performance.py` and `services/mlx-worker-python/tests/test_pr_scoped_performance.py`.

## Slice

1. Add a fast path in `build_scope_report(...)` that returns an empty matched-probe index set when the direct changed path set is empty.
2. Preserve force-all behavior: force-all inputs still select all probes, but they do not need matched-probe glob scanning when there are no direct paths.
3. Add a regression test that monkeypatches the matcher to prove empty direct paths do not scan probe watch globs.

## Success metrics

- Focused pytest for the changed behavior passes.
- Changed-scope coverage for `pr_scoped_performance.py` and the focused test scope is at least 95%.
- Registered `pr-scoped-performance-scope-matcher` probe reports lower or non-regressed `elapsed_ms_mean` for the scope matcher workload.
