# PR-scoped performance report result path generator sort

## Scope

This Python-only performance slice targets `scripts/pr_scoped_performance_report.py` in the `_load_results()` helper used by PR-scoped performance report assembly. Behavior remains unchanged: the loader scans the results directory with `os.scandir`, keeps deterministic JSON path ordering, reads JSON files as bytes, ignores non-dict payloads, and returns an empty result list when the directory cannot be scanned.

## Registered probe

The affected path is covered by the registered PR-scoped probe `pr-scoped-performance-report-results-scandir` in `infra/perf/pr_scoped_probes.json`. This slice keeps the focused `test_command`, `coverage_command`, and `probe_command` entries and compares the existing elapsed-time metrics without adding instrumentation overhead to the measured path.

## Implementation plan

1. Replace the `sorted([...])` list-comprehension input with a generator expression so `sorted()` materializes only its internal sorted list.
2. Keep the module-level binary open binding and `json.loads(handle.read())` parsing path unchanged.
3. Keep `scripts/pr_scoped_performance_report_results_probe.py` aligned with the registered command so base/head elapsed metrics are comparable.
4. Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux before opening the PR.

## Verification boundary

This slice is Python-only and locally verifiable on Linux. GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.
