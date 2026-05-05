# Training Dataset Validation Sample Limit Optimization

## Goal

Align local training dataset validation preview loading with the existing training sample `sample_limit` behavior so smoke and preview paths do not parse an entire `valid.jsonl` file when callers request only a bounded sample.

## Touched Files

- `services/mlx-worker-python/worker/model_ops/training_dataset.py`
- `services/mlx-worker-python/tests/test_training_dataset_builder.py`
- `infra/perf/pr_scoped_probes.json` if CI-scoped probe registration is needed

## Linux Verification Path

This is a Python-only slice and is locally verifiable on Linux.

## Performance Probe

Use a synthetic local dataset package with one training row and a large `valid.jsonl`, then call `load_training_dataset_package(..., sample_limit=1)` while measuring elapsed time and peak traced allocation. The expected improvement is O(total validation rows) to O(sample_limit) validation JSONL parsing for preview/smoke loads.

## Success Metrics

- Focused pytest passes for training dataset builder coverage.
- Changed-scope coverage is at least 95% for changed executable Python lines.
- The local probe returns the same one validation sample while materially reducing elapsed time and/or peak memory versus `origin/main`.
