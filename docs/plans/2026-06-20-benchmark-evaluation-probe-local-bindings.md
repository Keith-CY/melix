# Benchmark Evaluation Probe Local-Binding Slice

## Scope

This Python-only performance slice is limited to `worker.productization.benchmark_evaluation_report._collect_benchmark_probe_metrics`.

## Optimization

The benchmark/evaluation report hot path scans large request-row bundles and aggregates fixed probe keys. The behavior remains unchanged while the inner aggregation loop now binds the fixed probe-key containers and helper callables to locals once per call. This avoids repeated module-global lookups in the row/key loop without changing label generation, numeric conversion, or aggregate finalization.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `benchmark-evaluation-report-running-aggregates` in `infra/perf/pr_scoped_probes.json`, including focused `test_command`, `coverage_command`, and `probe_command` entries. Local Linux verification uses that registered probe; GitHub Actions PR-scoped performance remains the merge gate.

## Verification Plan

- Run the focused benchmark evaluation report tests.
- Run the registered changed-scope coverage command and require at least 95% for the touched scope.
- Run the registered probe locally on Linux against the current worktree.
- Run the PR-scoped performance workflow in CI and merge only after green checks and an acceptable registered probe report.
