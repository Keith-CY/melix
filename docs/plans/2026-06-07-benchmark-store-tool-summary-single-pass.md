# Benchmark Store Tool Summary Single-Pass Aggregation

## Scope

This Python-only performance slice is limited to `BenchmarkStore._attach_matrix_tool_turn_summary_fields(...)` in `services/mlx-worker-python/worker/productization/benchmark_store.py`.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe `benchmark-store-matrix-streaming` in `infra/perf/pr_scoped_probes.json`. The registry entry already provides focused `test_command`, `coverage_command`, and `probe_command` entries for the benchmark store implementation, focused tests, and `scripts/benchmark_store_probe.py`.

## Plan

1. Keep behavior unchanged for empty rows, wrong row types, pre-populated summary rows, and unmatched summary cells.
2. Collapse the separate request-row type check, tool-field presence scan, and aggregate pass into one request-row pass.
3. Run the registered focused tests, changed-scope coverage, `git diff --check`, and the registered local Linux probe before opening the PR.
4. Use GitHub Actions and the registered PR-scoped performance report as the merge gate.

## Metrics

Primary metric: lower `elapsed_ms_mean` from `benchmark-store-matrix-streaming`.
Secondary metric: lower or stable `peak_bytes_mean`; emitted row counts must remain unchanged.
