# Benchmark Report Metric Direction Cache Performance Slice

## Summary

Optimize benchmark/evaluation report row construction by caching metric-direction classification by metric suffix.

## Goals

1. Keep benchmark/evaluation report output unchanged.
2. Avoid repeatedly scanning the same metric-key fragments while building large comparison reports.
3. Validate the Python slice locally on Linux with the registered PR-scoped performance probe.

## Scope

- `services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py`
- `services/mlx-worker-python/tests/test_benchmark_evaluation_report.py`
- Registered probe `benchmark-evaluation-report-running-aggregates` in `infra/perf/pr_scoped_probes.json`.

## Design

`build_benchmark_evaluation_report()` calls `_metric_direction()` once for every emitted row. Large benchmark and evaluation exports create many rows that share the same final metric key, such as `prefill_ms_mean`, `decode_ms_mean`, or `failed_count`, while differing only in the suite/context label prefix.

This slice keeps `_metric_direction(metric_name)` as the public internal helper, but delegates the suffix-only classification to an unbounded `lru_cache`. The cache key is the final metric suffix after `rsplit(".", 1)`, so repeated labels reuse the same fragment-scan result without changing direction semantics.

## Success Metrics

- Focused benchmark/evaluation report tests pass.
- Changed-scope coverage remains at or above the repository requirement.
- Registered probe `benchmark-evaluation-report-running-aggregates` reports lower `elapsed_ms_mean` for the PR head than the base checkout without increasing `peak_bytes_mean` beyond the configured warning threshold.

## Known Constraints

- The local Linux probe is the validation source for this Python slice. CI reruns the same registered probe for base/head comparison before merge.
