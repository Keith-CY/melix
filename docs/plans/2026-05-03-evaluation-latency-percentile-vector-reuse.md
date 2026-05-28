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
- A 2026-05-28 follow-up micro-slice keeps the same behavior and one-sort invariant while inlining the two fixed percentile calculations inside `_latency_stats()`. The previous class-attribute binding step is already present on `main`, so this slice removes the remaining two `_ordered_percentile(...)` helper calls from the hot return path instead of rebinding them again.
- Latency summary outputs (`mean`, `p50`, `p95`, `max`) remain unchanged.
- Focused changed-scope coverage for touched executable files is at least 95%.
- The registered local probe must show stable or lower `elapsed_ms_mean` versus `origin/main`; `sorted_calls_mean` must remain `1.0`.

## Verification Commands

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q <focused tests>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q <focused tests>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/engine/evaluation_core.py services/mlx-worker-python/tests/test_evaluation_core.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/pr_scoped_performance_run.py --probe-id evaluation-latency-percentile-vector-reuse --base-ref origin/main --samples 3 --warmup 1 --output <json>
git diff --check
```