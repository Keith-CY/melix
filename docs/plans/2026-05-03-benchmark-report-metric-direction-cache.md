# Benchmark Report Metric Direction Cache

## Scope

This Python-only performance slice keeps benchmark/evaluation report behavior
unchanged while narrowing repeated metric-row finalization in
`worker/productization/benchmark_evaluation_report.py`.

The affected path is covered by the registered PR-scoped probe
`benchmark-evaluation-report-running-aggregates` in
`infra/perf/pr_scoped_probes.json`. The registry entry already provides focused
`test_command`, `coverage_command`, and `probe_command` entries for this module.

## Change

`_metric_direction()` now caches full metric-name lookups. The existing
`_metric_key_direction()` cache still handles suffix classification, while this
slice avoids repeating the `rsplit()` and nested cache lookup for the same large
metric set across repeated report builds.

## Verification

Run the registered focused commands locally on Linux:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_benchmark_evaluation_report.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_benchmark_evaluation_report.py && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage report -m services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py services/mlx-worker-python/tests/test_benchmark_evaluation_report.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 /tmp/run_benchmark_report_probe.py
```

Local Linux probe comparison used five registered probe invocations per side:
`origin/main` mean `152.7841158 ms`; head mean `145.685022 ms`; delta
`-7.0990938 ms` (`1.0487x`, `4.65%` faster). The PR-scoped performance workflow
remains the merge gate for the registered CI probe report.
