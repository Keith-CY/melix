# PR-scoped report results in-place path collection

## Scope

This Python-only performance slice is limited to `scripts/pr_scoped_performance_report.py::_load_results`, the helper that loads per-probe JSON result files before rendering the PR-scoped performance report.

## Registered probe

The affected path is already covered by the registered PR-scoped probe `pr-scoped-performance-report-results-scandir` in `infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`, `coverage_command`, and `probe_command` entries for `scripts/pr_scoped_performance_report.py`, `scripts/pr_scoped_performance_report_results_probe.py`, and focused PR-scoped performance tests.

## Optimization plan

1. Preserve deterministic path ordering and existing JSON filtering behavior.
2. Replace `sorted(...)` over a generator with an explicit list append loop plus in-place `list.sort()`, preserving the existing path-order contract while avoiding generator/sorted call overhead in the hot result scan.
3. Keep `os.scandir`, binary reads, module-level `_OPEN`, and no pre-existence stat checks.
4. Verify focused tests, changed-scope coverage, and the registered probe locally on Linux before PR.

## Expected metrics direction

The registered probe should report lower or stable `elapsed_ms_mean` / `elapsed_ms_min` for directories with many result JSON files because result path collection avoids the generator-to-sorted pipeline while retaining the same deterministic sort order.

## Linux validation boundary

This slice is Python-only and fully locally validated on Linux. GitHub Actions PR-scoped performance remains the merge gate.
