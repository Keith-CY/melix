# Training Dataset Token Percentile Optimization Plan

## Goal

Reduce redundant sorting work in `services/mlx-worker-python/worker/model_ops/training_dataset.py` when building training-dataset token statistics, while preserving output values and Linux-local verification.

## Constraints

- Host verification is Linux-only.
- Scope must stay inside Python worker and PR-scoped performance CI.
- Changes must remain behavior-preserving for dataset inspection and manifest token statistics.
- Automated coverage for touched executable Python files must be at least 95% before commit.

## Touched Files

- `services/mlx-worker-python/worker/model_ops/training_dataset.py`
- `services/mlx-worker-python/tests/test_training_dataset_builder.py`
- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Optimization Slice

1. Replace repeated percentile sorting for prompt/completion/total token lists with one pre-sort per list.
2. Keep `sample_count`, means, percentiles, and maxima identical.
3. Register a PR-scoped performance probe for the touched path so GitHub can compare `origin/main` vs PR head.

## Performance Probe

- **Probe ID:** `training-dataset-token-percentiles-single-sort`
- **Local measurement:** synthetic large-sample benchmark around `_build_quality_and_token_stats(...)` with fixed prompt/completion samples.
- **PR-scoped CI measurement:** base-vs-head probe in `pr_scoped_performance.py` that records:
  - `elapsed_ms_mean`
  - `sample_count`
- **Success metric:** identical token-stat outputs with lower `elapsed_ms_mean` on the synthetic probe.

## Verification Commands

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage report -m services/mlx-worker-python/worker/model_ops/training_dataset.py services/mlx-worker-python/worker/productization/pr_scoped_performance.py services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" python scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id training-dataset-token-percentiles-single-sort --base-repo /root/.openclaw/workspace/melix --head-repo "$PWD" --output /tmp/melix-training-dataset-probe.json
git diff --check
```
