# Benchmark Evaluation Report Label Memoization Plan

## Goal

Reduce repeated string assembly in the benchmark evaluation report hot path by memoizing benchmark row labels so repeated row shapes reuse the same label instead of rebuilding identical `suite/context/generation/batch/concurrency` strings for every row.

## Linux-Only Constraint

This slice is limited to the Python benchmark evaluation report implementation and its focused tests so it can be fully verified on Linux.

## Touched Files

- `services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py`
- `services/mlx-worker-python/tests/test_benchmark_evaluation_report.py`

## Optimization Slice

- Add a tiny internal label-cache helper keyed by the benchmark row shape used to construct context, batch, and matrix probe labels.
- Reuse cached labels in `_collect_benchmark_probe_metrics(...)` and the matrix-summary metric collection path.
- Preserve metric names, ordering, and report output exactly.
- Add focused regression coverage proving repeated identical row shapes only build a label once while keeping emitted metric keys unchanged.

## Performance Probe

Use the already-registered PR-scoped performance probe `benchmark-evaluation-report-running-aggregates`, which compares `build_benchmark_evaluation_report(...)` on a large synthetic export bundle and reports:

- `elapsed_ms_mean`
- `peak_bytes_mean`

## Success Metrics

- Report rows and summary remain identical for existing focused tests.
- Changed executable scope coverage is at least 95%.
- The registered local probe shows lower `elapsed_ms_mean` than `origin/main` for the synthetic benchmark evaluation report path.

## Verification Commands

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_benchmark_evaluation_report.py`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_benchmark_evaluation_report.py && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py services/mlx-worker-python/tests/test_benchmark_evaluation_report.py`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 -c "import json; from pathlib import Path; from worker.productization.pr_scoped_performance import _probe_benchmark_evaluation_report as probe; print(json.dumps(probe(Path.cwd()), sort_keys=True))"`
- `git diff --check`
