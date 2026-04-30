# Benchmark Evaluation Report Streaming Aggregation Plan

## Context

This Linux-only optimization slice targets `services/mlx-worker-python` and avoids Swift or macOS-only surfaces.

## Goal

Reduce redundant memory use in `worker/productization/benchmark_evaluation_report.py` by replacing per-metric `list[float]` accumulation with running sum/count aggregation for benchmark probe metrics and evaluation sample probe metrics while preserving all output keys and values.

## Touched Files

- `services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py`
- `services/mlx-worker-python/tests/test_benchmark_evaluation_report.py`

## Constraints

- Preserve report schema, metric names, numeric values, ordering, and warning semantics.
- Keep the change locally verifiable on Linux with focused pytest and coverage.
- Keep the slice small and avoid unrelated refactors.

## Probe

Create a self-contained Python measurement script that builds a large synthetic benchmark/evaluation bundle and compares the current `origin/main` implementation against the branch implementation for identical report output, elapsed time, and peak traced allocation.

## Success Metrics

- Focused pytest for `test_benchmark_evaluation_report.py` passes.
- Changed executable scope coverage is at least 95%.
- Performance probe shows reduced peak traced allocation for `build_benchmark_evaluation_report(...)` while preserving identical rows/summary output.
- `git diff --check` passes.
