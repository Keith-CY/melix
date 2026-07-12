# PR-scoped Performance Report Result Suffix Check

## Scope

This Python-only performance slice is limited to `scripts/pr_scoped_performance_report.py` result loading.

`_load_results(...)` scans a PR-scoped performance results directory with `os.scandir()`, filters JSON result files, sorts the discovered paths for deterministic report output, and then parses each result. The remaining per-entry filter used `entry.name[-5:] == ".json"`, allocating a short suffix string for every directory entry.

This slice keeps the same `os.scandir()` traversal, deterministic sorting, binary JSON reads, non-dict filtering, and missing-directory behavior, but uses `entry.name.endswith(".json")` for the suffix check. That avoids per-entry slice allocation while preserving accepted filenames.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `pr-scoped-performance-report-results-scandir` in `infra/perf/pr_scoped_probes.json`. The entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `scripts/pr_scoped_performance_report.py`
- `scripts/pr_scoped_performance_report_results_probe.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

The probe creates 2,000 JSON result files plus a non-JSON file and measures `_load_results(...)` latency.

## Validation Plan

- Run the focused registered pytest command.
- Run changed-scope coverage via the registered coverage command.
- Run `scripts/pr_scoped_performance_report_results_probe.py` locally on Linux.
- Let the PR-scoped performance workflow validate the registered probe in CI before merge.

## Expected Impact

The registered probe should report lower or stable `elapsed_ms_mean` / `elapsed_ms_min` for report result loading by avoiding one short-lived string allocation per scanned directory entry.
