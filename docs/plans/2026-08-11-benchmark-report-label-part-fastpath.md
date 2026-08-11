# Benchmark Report Label Part Fast Path Plan

## Goal

Reduce per-row label formatting overhead in the Python benchmark evaluation report builder by avoiding an unnecessary `str.replace(" ", "_")` call for already-normalized label segments.

## Linux-Only Constraint

This slice is limited to Python report construction and can be fully verified on Linux. No Swift runtime behavior is changed.

## Touched Files

- `services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py`
- `services/mlx-worker-python/tests/test_benchmark_evaluation_report.py`
- `docs/plans/2026-08-11-benchmark-report-label-part-fastpath.md`

## Optimization Slice

- Keep the existing benchmark label cache and output schema unchanged.
- Teach `_label_part(...)` to return string inputs directly when they contain no spaces.
- Preserve normalization for labels that do contain spaces and preserve numeric/stringified boundaries.

## Performance Probe

Use the registered PR-scoped performance probe `benchmark-evaluation-report-running-aggregates`, which covers:

- `services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py`
- `services/mlx-worker-python/tests/test_benchmark_evaluation_report.py`
- `scripts/benchmark_evaluation_report.py`
- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`

The probe reports:

- `load_input_ms_mean`
- `elapsed_ms_mean`
- `peak_bytes_mean`

## Success Metrics

- Focused benchmark evaluation report tests pass.
- Changed-scope coverage for the touched Python report code remains at least 95%.
- The registered local probe shows lower `elapsed_ms_mean` than the pre-change baseline for the synthetic benchmark evaluation report path.

## Verification Commands

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_benchmark_evaluation_report.py`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_benchmark_evaluation_report.py && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage report -m services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py services/mlx-worker-python/tests/test_benchmark_evaluation_report.py`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 -c "import json; from pathlib import Path; from worker.productization.pr_scoped_performance import _probe_benchmark_evaluation_report as probe; print(json.dumps(probe(Path.cwd()), sort_keys=True))"`
- `git diff --check`
