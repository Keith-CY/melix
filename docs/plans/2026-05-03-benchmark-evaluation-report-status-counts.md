# Benchmark Evaluation Report Status Count Fast Path

## Scope

This performance slice is limited to the Python benchmark/evaluation report builder in
`services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py`.
It keeps report semantics unchanged while reducing per-row status counting overhead in
`build_benchmark_evaluation_report()`.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`benchmark-evaluation-report-running-aggregates` in
`infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`,
`coverage_command`, and `probe_command` entries and measures `elapsed_ms_mean` and
`peak_bytes_mean` for large synthetic benchmark/evaluation bundles.

## Implementation Plan

1. Preserve the existing metric row schema, summary status precedence, and count fields.
2. Replace the per-row `match` dispatch and follow-up status selection checks with direct
   `if`/`elif` counters and a single precedence chain.
3. Add/keep regression coverage proving mixed warning, missing, and not-comparable counts
   remain exact.
4. Validate locally on Linux with focused pytest, changed-scope coverage, and the
   registered PR-scoped performance probe against `origin/main` and the branch worktree.

## Validation Boundary

This is a Python-only slice and is fully locally verifiable on Linux. Swift runtime effects
are not involved.

## Success Criteria

- Focused benchmark/evaluation report tests pass.
- Changed-scope coverage for the touched Python report/test scope is at least 95%.
- The registered probe shows a non-regressing or improved `elapsed_ms_mean` and no material
  memory regression before CI merge.
- PR-scoped performance CI selects and completes the registered probe before merge.
