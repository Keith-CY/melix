# Dataset quality output length direct loop

## Scope

Optimize one Python hot path in dataset quality summary construction: output-length collection for generated dataset samples in `worker.productization.dataset_preparation._quality_summary`.

## Registered probe

The affected path is already covered by the PR-scoped registered probe `dataset-quality-lengths-chain` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused test, changed-scope coverage, and probe commands for:

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_versioning.py`
- `scripts/dataset_quality_lengths_probe.py`

## Implementation plan

- Preserve completion and chat-message output length semantics.
- Replace the `chain(...)` + per-row helper call in the quality-summary hot path with a direct two-list loop that binds `append` once and inlines the existing length rules.
- Cover the batched helper directly with mixed completion, message, and malformed-message rows.

## Verification

- Run the registered probe locally on Linux before and after the change.
- Run the probe registry's focused test command.
- Run the probe registry's changed-scope coverage command and require at least 95% coverage.

## Boundary

This is a Python-only Linux-validated slice. No Swift runtime effect is claimed.
