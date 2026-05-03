# Benchmark evaluation sample direct-mean aggregation

## Goal

Reduce per-report overhead in `benchmark_evaluation_report` when finalizing evaluation sample probe metrics without changing metric names, values, or report status semantics.

## Scope

This slice is limited to:

- `services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py`
- `services/mlx-worker-python/tests/test_benchmark_evaluation_report.py`

## Registered probe coverage

The affected path is covered by the registered PR-scoped probe `benchmark-evaluation-report-running-aggregates` in `infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`, `coverage_command`, and `probe_command` entries and reports `elapsed_ms_mean`, `peak_bytes_mean`, and row-count correctness for the synthetic benchmark/evaluation report workload.

## Implementation plan

1. Add regression coverage proving evaluation sample metrics are finalized as direct means without routing through the generic aggregate finalizer.
2. Replace the generic finalizer call in `_collect_evaluation_sample_probe_metrics()` with direct `total / count` mean emission. Evaluation sample metrics always use the `_mean` suffix, unlike benchmark probe metrics that may emit rates or sums.
3. Run focused pytest, changed-scope coverage, `git diff --check`, and the registered probe locally on Linux against both `origin/main` and the branch.

## Success criteria

- Evaluation sample metric keys and values remain unchanged.
- Focused tests and changed-scope coverage pass.
- The registered local probe shows a lower `elapsed_ms_mean` without changing `row_count`.
- CI PR-scoped performance completes successfully before merge.
