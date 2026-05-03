# Benchmark/evaluation report summary key tuple hoist

## Scope

This performance slice is limited to `worker.productization.benchmark_evaluation_report`.
It keeps report semantics unchanged while reducing repeated tiny allocations in the
registered benchmark/evaluation report aggregation path.

## Optimization Hypothesis

`_collect_metrics()` iterates the same benchmark matrix summary metric names and
evaluation summary metric names for every report build. Those tuples were being
constructed inside the function on every call. Hoisting them to module-level
constants removes per-call tuple allocation while preserving the same iteration
order, metric names, and output rows.

## Registered Probe

- Probe ID: `benchmark-evaluation-report-running-aggregates`
- Registry: `infra/perf/pr_scoped_probes.json`
- Local Linux validation source: the registered focused tests, changed-scope
  coverage command, and the registered probe command.

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_benchmark_evaluation_report.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_benchmark_evaluation_report.py && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage report -m services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py services/mlx-worker-python/tests/test_benchmark_evaluation_report.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 -c "import json; from pathlib import Path; from worker.productization.pr_scoped_performance import _probe_benchmark_evaluation_report as probe; print(json.dumps(probe(Path.cwd()), sort_keys=True))"
git diff --check
```
