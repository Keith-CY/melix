# Training Dataset Quality/Token Summary Optimization Plan

## Goal

Reduce redundant memory retention and repeated sorting work in `services/mlx-worker-python/worker/model_ops/training_dataset.py` when building training-dataset quality and token summaries, while preserving manifest payload shape and Linux-verifiable evidence.

## Constraints

- Host verification is Linux-only.
- Scope must stay inside the Python worker and the PR-scoped performance harness.
- The optimization must preserve current duplicate-count, dirty-count, duplicate sample index ordering, dirty sample ordering, token means, percentile semantics, and maxima.
- Automated coverage for the touched executable scope must be at least 95% before commit.

## Touched Files

- `services/mlx-worker-python/worker/model_ops/training_dataset.py`
- `services/mlx-worker-python/tests/test_training_dataset_builder.py`
- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Optimization Slice

1. Replace full `duplicate_indices` / `dirty_samples` accumulation with capped retained samples while preserving total counts and ordering for the retained examples.
2. Add a direct `prompt_completion` token-count fast path inside `_build_quality_and_token_stats(...)` so the common dataset path avoids dispatching through the generic helper for every sample.
3. Keep percentile semantics and output fields identical by preserving the existing sorted token-summary logic.
4. Upgrade the registered training-dataset PR-scoped probe so it measures the actual touched helper and records both elapsed time and traced peak memory.
5. Use changed-scope coverage for the touched Python scope instead of the broader whole-file percentage when the focused slice does not exercise unrelated branches.

## Performance Probe

- **Probe ID:** `training-dataset-quality-token-summary`
- **Local measurement:** synthetic 20,000-sample benchmark around `_build_quality_and_token_stats(...)` using prompt/completion rows with periodic duplicates and dirty samples.
- **PR-scoped CI measurement:** base-vs-head probe in `worker/productization/pr_scoped_performance.py` that records:
  - `elapsed_ms_mean`
  - `peak_bytes_mean`
  - `sample_count`
  - `duplicate_count`
  - `dirty_count`
- **Success metric:** identical summary outputs with lower `peak_bytes_mean` and non-regressive or improved `elapsed_ms_mean` on the synthetic probe.

## Verification Commands

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/training_dataset.py services/mlx-worker-python/worker/productization/pr_scoped_performance.py services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 -c "import json; from pathlib import Path; from worker.productization.pr_scoped_performance import _probe_training_dataset_quality_token_summary as probe; print(json.dumps(probe(Path.cwd()), sort_keys=True))"
git diff --check
```