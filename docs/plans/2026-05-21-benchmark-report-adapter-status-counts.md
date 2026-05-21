# Benchmark report adapter status count slice

This Python-only performance slice keeps benchmark/evaluation report semantics unchanged while reducing redundant scans over generated agentic-adapter delta rows.

## Affected path

- `services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py`
- `services/mlx-worker-python/tests/test_benchmark_evaluation_report.py`
- `infra/perf/pr_scoped_probes.json`

The affected path is covered by the registered PR-scoped probe `benchmark-evaluation-report-running-aggregates`. The registry entry provides focused `test_command`, `coverage_command`, and `probe_command` entries. This slice also normalizes that registered probe command to invoke `python3` explicitly.

## Optimization

`build_benchmark_evaluation_report()` already computes primary metric-row status counts during the metric-row construction pass. Agentic-adapter delta rows, however, were scanned three separate times to count `warning`, `missing`, and `not_comparable` statuses.

This slice adds one small status-count helper and uses it for the adapter delta rows so each row's status is read once. The behavior is intentionally equivalent:

- the same three status classes feed the report summary;
- `ok` and other statuses remain non-counted;
- report status precedence remains `warning > missing > not_comparable > ok`.

## Verification plan

Run on Linux:

1. Focused regression test for single-read status counting.
2. Full benchmark-evaluation report tests through the registered focused command.
3. Changed-scope coverage through the registered coverage command.
4. Registered benchmark-evaluation report probe locally with the registry command.
5. GitHub Actions PR-scoped performance as the merge gate.

## Metrics

Primary metric: `elapsed_ms_mean` from the registered `benchmark-evaluation-report-running-aggregates` probe. Secondary metrics: `load_input_ms_mean`, `peak_bytes_mean`, `row_count`, and `sample_count`.
