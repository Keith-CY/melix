# Evaluation Latency Percentile Vector Reuse

## Goal

Eliminate duplicate sorting in `EvaluationCore._latency_stats()` by reusing one ordered latency vector for both `p50` and `p95` calculations, while preserving the current percentile interpolation semantics exactly.

## Linux-Only Constraint

This slice is confined to the Python worker and the PR-scoped performance harness, so it can be fully verified on Linux without macOS or Swift execution.

## Touched Files

- `services/mlx-worker-python/worker/engine/evaluation_core.py`
- `services/mlx-worker-python/tests/test_evaluation_core.py`
- `infra/perf/pr_scoped_probes.json`

## Probe Definition

Update the evaluation-scoped PR performance probe set with a dedicated `command_json` probe that exercises `_latency_stats()` on a large synthetic latency vector and records:

- `elapsed_ms_mean`
- `sorted_calls_mean`
- `sample_count`

The probe must be base-compatible so `origin/main` still runs successfully during base-vs-head comparison.

## Success Metrics

- `_latency_stats()` performs one sort per invocation instead of two.
- Latency summary outputs (`mean`, `p50`, `p95`, `max`) remain unchanged.
- Focused changed-scope coverage for touched executable files is at least 95%.
- Local probe shows lower elapsed time and fewer sort calls versus `origin/main`.

## Verification Commands

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q <focused tests>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q <focused tests>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/engine/evaluation_core.py services/mlx-worker-python/tests/test_evaluation_core.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/pr_scoped_performance_run.py --probe-id evaluation-latency-percentile-vector-reuse --base-ref origin/main --samples 3 --warmup 1 --output <json>
git diff --check
```