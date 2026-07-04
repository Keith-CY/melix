# PR-scoped Performance Report Result Loop Filter

## Scope

This Python-only performance slice is limited to `scripts/pr_scoped_performance_report.py` result loading.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `pr-scoped-performance-report-results-scandir` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for this script, its probe script, and the focused PR-scoped performance tests.

## Optimization

`_load_results()` already uses `os.scandir()` and binary JSON reads. This slice keeps those semantics but replaces the result-path list comprehension with a direct `os.scandir()` loop that binds `result_paths.append` once while filtering JSON result files. The load loop also binds `open` once before iterating over the sorted paths. The behavior remains deterministic by sorting the collected paths before reading result payloads.

## Validation plan

1. Run the registered focused test command for `pr-scoped-performance-report-results-scandir` locally on Linux.
2. Run the registered changed-scope coverage command and remove generated `coverage.json` afterwards.
3. Run `scripts/pr_scoped_performance_report_results_probe.py` locally before and after the slice to compare result-load elapsed time.
4. Use the PR-scoped performance CI report as the merge gate before squash merging.