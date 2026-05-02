# Training dataset control-character fast path

## Context

This slice keeps the existing registered PR-scoped probe `training-dataset-token-percentiles-single-sort` as the validation surface for `services/mlx-worker-python/worker/model_ops/training_dataset.py`.

## Slice

The quality scanner calls `_contains_problematic_control_characters()` for every inspected prompt/completion segment. The prior implementation rebuilt the allowed newline/carriage-return/tab set inside the generator expression while scanning text. This slice hoists that membership set to a module constant and binds it locally in the helper so the per-character loop reuses one immutable container.

## Verification

Use the registered probe commands from `infra/perf/pr_scoped_probes.json`:

- focused `test_command` for training dataset and PR-scoped performance tests
- changed-scope `coverage_command`
- `probe_command` for `training-dataset-token-percentiles-single-sort`

This is a Python-only slice and is fully locally verifiable on Linux; CI remains the merge gate for the registered PR-scoped performance report.
