# Benchmark report delta classification slice

This Python-only performance slice keeps benchmark/evaluation report semantics unchanged while reducing repeated classification scans over comparison delta rows.

## Affected path

- `services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py`
- `services/mlx-worker-python/tests/test_benchmark_evaluation_report.py`
- `infra/perf/pr_scoped_probes.json`

The affected path is covered by the registered PR-scoped probe `benchmark-evaluation-report-running-aggregates`. The registry entry already provides focused `test_command`, `coverage_command`, and `probe_command` entries for the benchmark/evaluation report builder.

## Optimization

`_comparison_section()` materializes benchmark/evaluation metric deltas, then derives comparison buckets for regressions, improvements, and unchanged rows. Previously those three buckets were built with three separate list comprehensions over the combined delta rows. This slice adds a small `_classify_comparison_delta_rows()` helper that classifies the same rows in one pass.

The behavior is intentionally equivalent:

- `result == "fail"` rows still populate `regressions`;
- lower-is-better negative deltas and higher-is-better positive deltas still populate `improvements`;
- zero numeric deltas still populate `unchanged`;
- rows can still appear in more than one bucket when their independent predicates match.

## Verification plan

Run on Linux:

1. Focused regression test proving each row's `result` and `delta` are read once during classification.
2. Full benchmark-evaluation report tests through the registered focused command.
3. Changed-scope coverage through the registered coverage command.
4. Registered benchmark-evaluation report probe locally with the registry command, comparing `origin/main` baseline to this slice.
5. GitHub Actions PR-scoped performance as the merge gate.

## Metrics

Primary metric: `elapsed_ms_mean` from the registered `benchmark-evaluation-report-running-aggregates` probe. Secondary metrics: `load_input_ms_mean`, `peak_bytes_mean`, `row_count`, and `sample_count`.
