# Training dataset token stats single-pass optimization

## Goal

Reduce redundant work in `services/mlx-worker-python/worker/model_ops/training_dataset.py` when computing `prompt_completion` token statistics by keeping the direct fast path but avoiding extra materialization and repeated list-comprehension passes.

## Scope

- `services/mlx-worker-python/worker/model_ops/training_dataset.py`
- `services/mlx-worker-python/tests/test_training_dataset_builder.py`
- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- Reuse the existing scoped CI probe registration for `training-dataset-token-percentiles-single-sort`

## Linux-only constraint

This slice is Python-only and must be verified locally on Linux with focused pytest, changed-scope coverage, and an explicit local performance probe before commit.

## Intended change

- Keep `_collect_token_stats(..., "prompt_completion")` on a specialized fast path.
- Replace the current materialize-plus-multiple-list-comprehensions approach with one direct pass over the samples.
- Preserve the existing output schema and metric semantics exactly.
- Add or update focused regression tests to prove the optimized path still uses the specialized direct logic and handles non-list iterables correctly.

## Performance probe

Use the already-registered PR-scoped performance probe:

- Probe id: `training-dataset-token-percentiles-single-sort`
- Local command:
  - `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 -c "import json; from pathlib import Path; from worker.productization.pr_scoped_performance import _probe_training_dataset_token_percentiles as probe; print(json.dumps(probe(Path.cwd()), sort_keys=True))"`

## Success metrics

- `elapsed_ms_mean` from the training-dataset token-percentiles probe improves versus `origin/main`, or at minimum does not regress while removing redundant traversal/materialization.
- `prompt_tokens_p95`, `total_tokens_p95`, and `sample_count` remain unchanged.
- Changed executable scope coverage is at least 95%.

## Verification commands

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/training_dataset.py services/mlx-worker-python/worker/productization/pr_scoped_performance.py services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 -c "import json; from pathlib import Path; from worker.productization.pr_scoped_performance import _probe_training_dataset_token_percentiles as probe; print(json.dumps(probe(Path.cwd()), sort_keys=True))"`
```
