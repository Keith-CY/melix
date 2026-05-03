# Training dataset duplicate-key fast path

## Context

This Linux-only optimization slice targets `services/mlx-worker-python/worker/model_ops/training_dataset.py`.
The current `origin/main` implementation of `_build_quality_and_token_stats()` computes duplicate detection keys by hashing a JSON-sorted canonical string for every sample, even for the hot `prompt_completion` path where the relevant shape is already just `prompt` plus `completion`.

The affected path is already covered by the registered PR-scoped probe `training-dataset-token-percentiles-single-sort` in `infra/perf/pr_scoped_probes.json`, so this slice can be locally verified on Linux and then validated again in CI.

## Goal

Reduce redundant per-sample work in the prompt/completion quality scan by reusing the native prompt/completion fields directly for duplicate detection while preserving duplicate counts, dirty-sample semantics, and token statistics.

## Touched files

- `services/mlx-worker-python/worker/model_ops/training_dataset.py`
- `services/mlx-worker-python/tests/test_training_dataset_builder.py`
- `docs/plans/2026-05-02-training-dataset-duplicate-key-fast-path.md`

## Probe and success metrics

- **Scoped CI probe:** `training-dataset-token-percentiles-single-sort`
- **Local probe command:** existing `probe_command` from `infra/perf/pr_scoped_probes.json`
- **Primary success metric:** lower `elapsed_ms_mean` on the local training-dataset probe versus current `origin/main`
- **Secondary metric:** no material regression in `peak_bytes_mean`
- **Correctness gates:**
  - focused pytest passes for touched training-dataset / scoped-performance tests
  - changed-scope coverage is at least 95%
  - duplicate and dirty counts remain unchanged on the synthetic probe workload

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/training_dataset.py services/mlx-worker-python/worker/productization/pr_scoped_performance.py services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 -c "import json; from pathlib import Path; from worker.productization.pr_scoped_performance import _probe_training_dataset_token_percentiles as probe; print(json.dumps(probe(Path.cwd()), sort_keys=True))"
```

## Risks

- Prompt/completion duplicate detection must preserve current semantics for non-string values after coercion.
- Non-`prompt_completion` sample formats must keep using the generic canonical path.
- If the local probe does not beat `origin/main`, abandon the slice rather than pushing a semantic no-op refactor.
