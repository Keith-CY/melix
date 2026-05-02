# Benchmark Evaluation Probe Key Scan Slice

## Scope

This Python-only slice narrows the hot path in
`services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py`.
The registered PR-scoped probe `benchmark-evaluation-report-running-aggregates`
already covers this file with focused test, coverage, and probe commands in
`infra/perf/pr_scoped_probes.json`.

## Optimization

The report collectors now scan the fixed registered probe-key tuples directly
instead of walking every row item and filtering unrelated fields. This preserves
metric aggregation semantics while reducing per-row dictionary iteration work in
large benchmark/evaluation export bundles.

## Verification

Linux-local verification commands for this slice:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_benchmark_evaluation_report.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_benchmark_evaluation_report.py && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage report -m services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py services/mlx-worker-python/tests/test_benchmark_evaluation_report.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 /tmp/melix_probe_benchmark_evaluation_report.py
```

## Metrics

Local old/new module comparison against `origin/main` on the registered synthetic
bundle:

- old mean: `155.946 ms`
- new mean: `141.918 ms`
- delta: `-14.028 ms`
- speedup: `1.0988x`
- row count parity: `5990`
- peak bytes mean parity: `3904530.4`

PR-scoped performance CI remains the merge gate for the registered probe report.
