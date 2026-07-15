# PR-scoped Performance Report Result Path Collection Slice

## Scope

This Python-only performance slice covers the result-file collection phase in
`scripts/pr_scoped_performance_report.py`.

The affected path is already covered by the registered PR-scoped performance
probe `pr-scoped-performance-report-results-scandir` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries for:

- `scripts/pr_scoped_performance_report.py`
- `scripts/pr_scoped_performance_report_results_probe.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Optimization

Keep the existing `os.scandir()` traversal and binary `json.loads()` parsing.
The first slice collected sorted JSON result paths directly from a list
comprehension passed to `sorted(...)`, removing the explicit temporary append
binding and post-build in-place sort.

This follow-up slice sorts the filtered `DirEntry` objects by `entry.name` and
opens each entry through `entry.path`. That avoids building a separate list of
full path strings before sorting while preserving deterministic result-name
order, ignored non-JSON files, missing-directory behavior, and dictionary-only
payload loading.

## Verification

Local Linux validation uses the registered focused tests, changed-scope coverage
command, and registered PR-scoped performance probe. The GitHub Actions
PR-scoped performance workflow remains the merge gate for CI validation.
