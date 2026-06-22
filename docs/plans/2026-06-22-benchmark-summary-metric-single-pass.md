# Benchmark summary metric single-pass slice

## Scope

This Python-only performance slice is limited to `worker.productization.benchmark_evaluation_report._load_batch_run_summary_bundle(...)`.

## Motivation

Batch run summary bundles expose per-model `metric_fields` dictionaries that may contain both `bench.*` and `eval.*` entries. The previous conversion path scanned the same dictionary twice: once to materialize benchmark metrics and once to materialize evaluation rows. Large scheduled benchmark batches can include many models and many metrics per model, so the duplicate scan adds avoidable per-report overhead.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `benchmark-evaluation-report-running-aggregates` in `infra/perf/pr_scoped_probes.json`. The registry entry already includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py`
- `services/mlx-worker-python/tests/test_benchmark_evaluation_report.py`
- `scripts/benchmark_evaluation_report.py`
- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`

The probe reports `load_input_ms_mean`, `elapsed_ms_mean`, and `peak_bytes_mean` for the benchmark/evaluation report path.

## Implementation Plan

1. Add a regression test proving batch summary `metric_fields.items()` is scanned once while preserving benchmark and evaluation row output.
2. Replace the two-pass `metric_fields` handling with one loop that dispatches valid numeric `bench.*` and `eval.*` metrics to their existing output shapes.
3. Run the focused test, registered coverage command, and registered probe locally on Linux.

## Validation Boundary

This slice changes Python code and is locally verifiable on Linux. The PR-scoped performance workflow remains the merge gate for the registered CI probe result.
