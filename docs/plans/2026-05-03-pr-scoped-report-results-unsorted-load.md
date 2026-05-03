# PR-scoped report results unsorted load

## Goal

Reduce the Python PR-scoped performance report result-loading overhead by removing a redundant sort from `scripts/pr_scoped_performance_report.py`.

## Scope

- `scripts/pr_scoped_performance_report.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Probe coverage

The affected path is already covered by registered PR-scoped probe `pr-scoped-performance-report-results-scandir` in `infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`, `coverage_command`, and `probe_command` entries for local Linux validation and CI validation.

## Implementation plan

1. Keep the loader on `os.scandir()` and binary `json.loads()` reads.
2. Stop sorting loaded result paths before parsing. The report builder maps results by probe ID and emits rows in `selected_probes` order, so file iteration order does not define report row order.
3. Update the focused regression test so it validates payload preservation rather than incidental loader ordering.
4. Run the registered focused test, changed-scope coverage, and local probe command.

## Success metrics

- Focused test and changed-scope coverage pass with >=95% for touched Python scope.
- Registered probe `elapsed_ms_mean` and/or `elapsed_ms_min` improves versus the pre-change baseline.
- CI PR-scoped performance workflow selects and completes `pr-scoped-performance-report-results-scandir` successfully.
