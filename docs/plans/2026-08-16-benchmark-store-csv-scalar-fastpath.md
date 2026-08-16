# Benchmark store CSV scalar fast path

## Scope

This Python-only performance slice is limited to CSV value normalization inside
`services/mlx-worker-python/worker/productization/benchmark_store.py` when matrix
benchmark summary/request rows are persisted.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`benchmark-store-matrix-streaming` in `infra/perf/pr_scoped_probes.json`. That probe
watches `benchmark_store.py`, `test_benchmark_store.py`, `test_pr_scoped_performance.py`,
and `scripts/benchmark_store_probe.py`, and it provides focused `test_command`,
`coverage_command`, and `probe_command` entries.

## Optimization hypothesis

Matrix benchmark rows serialize many CSV scalar cells (strings, integers, floats,
booleans, and empty values). The generic export `_csv_value` helper must check
list, tuple, and dict cases for every scalar. This slice keeps the generic helper
as the fallback for containers and custom objects, but adds a benchmark-store local
scalar fast path before writing CSV rows.

## Verification path

Run the registered benchmark-store focused tests, changed-scope coverage, and
`benchmark_store_probe.py` locally on Linux. The expected signal is lower
`elapsed_ms_mean` for the matrix streaming probe while preserving CSV output parity
for common scalar and container values.

## Success criteria

- Focused benchmark-store and PR-scoped probe tests pass.
- Changed-scope automated coverage for touched paths is at least 95%.
- The local registered probe shows improvement or a clear non-regression.
- GitHub Actions PR-scoped performance for `benchmark-store-matrix-streaming`
  completes successfully before merge.
