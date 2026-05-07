# Training Dataset Validation Split Partial Selection

## Goal

Reduce redundant sorting work in automatic training-dataset validation splitting.

## Scope

- `services/mlx-worker-python/worker/model_ops/training_dataset.py`
- `services/mlx-worker-python/tests/test_training_dataset_builder.py`
- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Linux-only constraint

This is a Python worker slice and can be verified on Linux with focused pytest, changed-scope coverage, and a PR-scoped performance probe.

## Optimization

`_deterministic_validation_split(...)` previously sorted every `(digest, index)` pair even though it only needs the lowest `validation_count` items. Replace the full sort with `heapq.nsmallest(validation_count, ...)` while preserving tuple tie-breaking and the existing original-order output contract for train and validation rows.

## Probe

Register `training-dataset-validation-split-nsmallest` in `infra/perf/pr_scoped_probes.json`.

The probe builds a deterministic synthetic prompt/completion dataset, calls `_deterministic_validation_split(...)` repeatedly, verifies the selected validation count and checksum, and reports:

- `elapsed_ms_mean` lower is better
- `peak_bytes_mean` lower is better
- `validation_count` stable structural metric
- `checksum` stable structural metric

## Success metrics

- Focused pytest passes for the touched training dataset behavior and PR-scoped registry checks.
- Changed-scope executable coverage is at least 95%.
- Local base-vs-head probe shows lower elapsed time and/or memory while preserving structural metrics.
- `git diff --check` passes.
