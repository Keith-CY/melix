# PR-scoped Selected Probe Index Iteration

## Scope

This Python-only performance slice is limited to the PR-scoped performance scope-selection hot path in `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`.

The affected path is already covered by registered PR-scoped probe `pr-scoped-performance-scope-matcher` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for the scope matcher, coverage path selection, and command-summary behavior.

## Optimization

For non-force-all scope reports, `_scope_selection_uncached()` already computes the matched probe indexes. The current implementation still walks every registered probe to emit selected probe dictionaries and matched probe IDs. This slice will reuse the matched indexes directly, preserving registry order via sorted indexes while skipping the extra full registry scans for the common small-selection case.

## Verification

Run the registered focused test command, changed-scope coverage command, and local registered probe on Linux before opening the PR. The PR-scoped performance GitHub Actions workflow remains the merge gate for the registered probe result in CI.

## Expected Metrics

- `build_scope_report_ms_mean`: lower is better; expected to improve for small changed-file sets that select a subset of probes.
- `selected_probe_count_mean`: unchanged.
- `force_all_selected_mean`: unchanged.

## Follow-up: selected coverage path filtering

This follow-up slice keeps the same registered probe and narrows the coverage-path
attachment step after scope selection. For non-force-all scope reports,
`_selected_probes_with_coverage_paths()` now passes the selected probe IDs into
the coverage-path collector so the wildcard matcher set is reduced to the probes
that will actually be emitted. This preserves coverage-path output while avoiding
unneeded wildcard checks against unselected probes in the common small-selection
case.

Verification remains the registered `pr-scoped-performance-scope-matcher` focused
test, coverage, and probe commands on Linux, with PR-scoped performance CI as the
merge gate.
