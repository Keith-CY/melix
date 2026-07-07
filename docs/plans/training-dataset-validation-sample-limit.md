# Training Dataset Validation Sample Limit Optimization

## Goal

Apply `sample_limit` consistently to both `samples.jsonl` and `valid.jsonl` when loading a local training dataset package. Limited preview/smoke paths should not parse or normalize the entire validation split when only a bounded sample is requested.

This follow-up micro-slice keeps that behavior unchanged and reduces per-row JSONL iterator overhead by binding JSON decode helpers and the sample-limit branch outside `_iter_dataset_package_jsonl_rows()`'s hot loop.

## Linux Constraint

This is a Python-only slice under `services/mlx-worker-python`, verifiable on Linux with focused pytest, changed-scope coverage, and a local synthetic performance probe.

## Touched Files

- `services/mlx-worker-python/worker/model_ops/training_dataset.py`
- `services/mlx-worker-python/tests/test_training_dataset_builder.py`

## Performance Probe

Synthetic local package with one training row and many validation rows. Measure `load_training_dataset_package(..., sample_limit=1)` before/after by comparing current branch against `origin/main` with elapsed time and peak traced allocation.

Success metrics:

- Preserve loaded sample and validation sample output for the first validation row.
- Avoid parsing invalid/tail validation rows after the limit.
- Reduce elapsed time and peak traced allocation for large validation files with `sample_limit=1`.

## Verification Commands

- Focused pytest for the new and adjacent sample-limit tests.
- Changed-scope coverage for touched executable Python/test lines, requiring at least 95%.
- `git diff --check`.
- Local base-vs-head performance probe with concrete metrics.

## PR-Scoped Performance CI

The affected path is covered by the registered `training-dataset-validation-sample-limit` PR-scoped probe in `infra/perf/pr_scoped_probes.json`. Its `test_command`, `coverage_command`, and `probe_command` entries cover the loader, focused training dataset tests, and `scripts/training_dataset_validation_limit_probe.py`.
