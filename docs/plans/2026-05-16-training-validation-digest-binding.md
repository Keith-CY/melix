# Training Validation Split Digest Binding Slice

## Scope

This Python-only performance slice is limited to the deterministic validation split helper in `services/mlx-worker-python/worker/model_ops/training_dataset.py`.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe `training-dataset-validation-split-nsmallest` in `infra/perf/pr_scoped_probes.json`.

The registered probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/model_ops/training_dataset.py`
- `services/mlx-worker-python/tests/test_training_dataset_builder.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Optimization Slice

`_deterministic_validation_split(...)` hashes every sample before selecting the deterministic train or validation subset. This slice binds `_canonical_sample_digest` into a local name before constructing the ranked-sample generator so the hot generator loop avoids repeated global lookup while preserving the existing heap selection and stable output ordering.

The change intentionally does not alter split sizing, digest contents, heap direction, or train/validation ordering semantics.

## Verification Plan

Run the registered focused tests, changed-scope coverage, and registered probe locally on Linux before pushing. Compare the registered probe output against a pre-change baseline captured from `origin/main` in the same worktree.

CI remains the merge gate for the registered PR-scoped performance report.
