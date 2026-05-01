# Training Dataset Token Stats Single-Pass Optimization Plan

## Goal

Reduce redundant work in `services/mlx-worker-python/worker/model_ops/training_dataset.py` by separating token-stat collection from quality-report collection when callers only need token statistics.

## Constraints

- Work is being performed from a Linux host.
- The slice must remain Python-only and locally verifiable.
- Behavior and output schema must remain unchanged.
- The existing PR-scoped performance probe must continue to validate the path.

## Touched Files

- `services/mlx-worker-python/worker/model_ops/training_dataset.py`
- `services/mlx-worker-python/tests/test_training_dataset_builder.py`
- `infra/perf/pr_scoped_probes.json` only if the existing probe coverage needs adjustment

## Problem Statement

`_build_token_stats()` currently delegates to `_build_quality_and_token_stats()`, which also computes duplicate digests and dirty-sample reasons. That extra quality work is unnecessary for token-stat-only callers and adds avoidable hot-path cost.

## Implementation Approach

1. Keep `_build_quality_and_token_stats()` for callers that need both quality and token statistics in one pass.
2. Introduce a token-stats-only helper that only computes sample count plus prompt/completion/total token summaries.
3. Route `_build_token_stats()` through the token-stats-only helper.
4. Add or update focused regression tests to prove `_build_token_stats()` no longer performs duplicate-digest or dirty-sample work while preserving output.

## Performance Probe

- Existing scoped probe: `training-dataset-token-percentiles-single-sort`
- Probe implementation: `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- Success metric: lower `elapsed_ms_mean` with unchanged `sample_count`, `prompt_tokens_p95`, and `total_tokens_p95`

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage report -m services/mlx-worker-python/worker/model_ops/training_dataset.py services/mlx-worker-python/worker/productization/pr_scoped_performance.py services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id training-dataset-token-percentiles-single-sort --base-repo . --head-repo . --output /tmp/melix-training-dataset-probe-head.json
git diff --check
```

## Success Criteria

- Focused tests pass.
- Automated coverage for the changed executable scope is at least 95%.
- The scoped performance probe reports improved `elapsed_ms_mean` with unchanged token-stat outputs.
- The change remains small and reviewable.
