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

## 2026-05-14 follow-up: high validation ratio complement selection

For high automatic validation ratios, the validation set is most of the dataset and
`heapq.nsmallest(validation_count, ...)` keeps a large heap. Select the smaller
complement instead: when `train_count < validation_count`, choose the largest
`train_count` digest/index pairs with `heapq.nlargest(...)`, then stream the
original samples once to preserve the existing output order contract. Low-ratio
splits keep the existing `nsmallest(...)` path.

The registered probe now uses a `0.95` validation ratio so the PR-scoped report
exercises the complement path. The registry command also uses `python3` for the
scheduled Linux runner.

## 2026-05-14 follow-up: split streaming branch specialization

Keep the same registered high-ratio probe and specialize the final original-order
streaming pass into separate high-ratio and low-ratio loops. This removes the
per-sample `validation_indices is None` branch from the hot loop while preserving
the same sorted digest selection and output ordering contracts.

## Success metrics

- Focused pytest passes for the touched training dataset behavior and PR-scoped registry checks.
- Changed-scope executable coverage is at least 95%.
- Local base-vs-head probe shows lower elapsed time and/or memory while preserving structural metrics.
- `git diff --check` passes.
