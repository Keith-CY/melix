# Training Quality/Token Stats Local Binding Optimization

## Goal

Reduce Python overhead in `training_dataset._build_quality_and_token_stats()` for large `prompt_completion` training datasets while preserving the single-pass quality and token-stat behavior.

## Constraints

- Host verification is Linux-only.
- The touched runtime path is Python under `services/mlx-worker-python`.
- The optimization is intentionally limited to one hot loop in `training_dataset.py`.
- The affected path is covered by the registered PR-scoped probe `training-dataset-token-percentiles-single-sort`, which declares focused test, coverage, and probe commands in `infra/perf/pr_scoped_probes.json`.

## Proposed Change

Bind hot-loop append methods and helper functions once before iterating samples in `_build_quality_and_token_stats()`, and route `prompt_completion` rows through a specialized dirty-sample checker that avoids building intermediate text-segment lists.

This keeps the existing semantics:

- duplicate detection still uses canonical sample digests;
- dirty-sample reporting still caps retained examples at `_QUALITY_REPORT_SAMPLE_LIMIT` while preserving total counts;
- `prompt_completion` still uses the direct whitespace-token fast path;
- non-`prompt_completion` formats still dispatch through `_sample_token_counts()`.

## Performance Probe

### Probe name

`training-dataset-token-percentiles-single-sort`

### Measurement path

The registered probe builds a large synthetic training dataset and repeatedly calls `_build_quality_and_token_stats(samples, "prompt_completion")`, recording mean elapsed time and peak bytes.

### Success metric

- Lower `elapsed_ms_mean` is better.
- Peak allocation should not materially regress.
- Token stats and quality counters must remain unchanged.

## Local Verification Commands

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/training_dataset.py services/mlx-worker-python/worker/productization/pr_scoped_performance.py services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id training-dataset-token-percentiles-single-sort --base-repo <base-repo> --head-repo <head-repo> --output <output-json>
git diff --check
```
