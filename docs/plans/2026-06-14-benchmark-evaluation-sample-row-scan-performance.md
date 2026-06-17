# Benchmark Evaluation Sample Row Scan Performance

## Status

Accepted for the 2026-06-14 performance slice.

## Context

The PR-scoped benchmark evaluation report probe exercises
`worker.productization.benchmark_evaluation_report` with large synthetic
benchmark and evaluation bundles. The evaluation sample collector walks every
sample row and previously checked each fixed sample probe key with membership
lookups before reading the value.

Sparse rows are common in report payloads: each row usually contains a small
subset of the known probe keys plus metadata. Repeating fixed-key membership
checks for every row adds unnecessary dictionary lookups in the report build
path.

## Slice

Change only the evaluation sample metric collector to iterate row items once and
filter keys through a precomputed probe-key set. This keeps the emitted metric
names and aggregation semantics unchanged while avoiding fixed-key membership
and index lookups on sparse rows.

## Validation

The affected path is covered by the registered PR-scoped probe
`benchmark-evaluation-report-running-aggregates` in
`infra/perf/pr_scoped_probes.json`. The probe includes focused test, coverage,
and probe commands for:

- `services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py`
- `services/mlx-worker-python/tests/test_benchmark_evaluation_report.py`

Local Linux validation should run the registered focused tests, changed-scope
coverage command, and registered probe. CI remains the source of truth for the
PR-scoped performance workflow report.

## Expected Metrics

The probe should show a lower or neutral `elapsed_ms_mean` for benchmark report
construction. `load_input_ms_mean` is not expected to change because this slice
only changes report aggregation after input loading.
