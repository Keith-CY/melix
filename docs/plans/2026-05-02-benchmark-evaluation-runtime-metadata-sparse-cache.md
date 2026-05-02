# Benchmark Evaluation Runtime Metadata Sparse Cache

## Scope

This performance slice targets `services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py` only. The report builder collects runtime metadata for benchmark and evaluation job groups while building PR benchmark/evaluation comparison reports.

## Probe Coverage

The affected path is covered by the registered PR-scoped performance probe `benchmark-evaluation-report-running-aggregates` in `infra/perf/pr_scoped_probes.json`.

The registered probe includes:

- `test_command` for `services/mlx-worker-python/tests/test_benchmark_evaluation_report.py`
- `coverage_command` for changed-scope coverage on the report builder and tests
- `probe_command` for `_probe_benchmark_evaluation_report`

## Change

Runtime metadata collection now creates per-key value sets lazily instead of preallocating empty sets for every registered runtime parameter key on each collection call. Output ordering still follows `_RUNTIME_PARAMETER_KEYS`, and value ordering remains sorted within each key.

## Success Criteria

- Focused benchmark evaluation report tests pass.
- Changed-scope coverage stays at or above 95%.
- Registered probe reports non-regressing `elapsed_ms_mean` and `peak_bytes_mean` versus `origin/main`.
