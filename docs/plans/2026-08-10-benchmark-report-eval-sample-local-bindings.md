# Benchmark Report Evaluation Sample Probe Local Bindings

## Scope

This Python-only performance slice is limited to evaluation sample probe metric
aggregation in `worker.productization.benchmark_evaluation_report`.

The registered benchmark-evaluation report probe spends part of report building
inside `_collect_evaluation_sample_probe_metrics(...)`, walking many sample rows
and repeatedly reading module-level constants and helper functions from globals.
This slice binds the hot-path key sets, float conversion helper, numeric aggregate
updater, and nested tool-metric `.get` method once per aggregation call while
preserving metric names, values, and failure-stage counts.

## Probe Coverage

The affected production path is covered by the registered PR-scoped probe
`benchmark-evaluation-report-running-aggregates` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` values for the report
builder and benchmark-evaluation report tests.

## Verification Plan

This slice is Python-only and locally verifiable on Linux:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_benchmark_evaluation_report.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_benchmark_evaluation_report.py && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage report -m services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py services/mlx-worker-python/tests/test_benchmark_evaluation_report.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id benchmark-evaluation-report-running-aggregates --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/benchmark_report_eval_sample_bindings_probe.json
```

## Success Criteria

- Focused benchmark-evaluation report tests pass.
- Changed-scope coverage for the touched report scope remains at least 95 percent.
- The registered probe reports lower `elapsed_ms_mean` on the optimized head.
