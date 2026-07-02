# Dataset registry single-directory split inference fast path

## Scope

This Python performance slice is limited to `worker.dataset_registry.catalog._inferred_split_and_config()`.
The registered PR-scoped probe is `dataset-registry-snapshot-inference-single-pass`, which covers:

- `services/mlx-worker-python/worker/dataset_registry/catalog.py`
- `services/mlx-worker-python/tests/test_dataset_registry.py`
- `scripts/dataset_registry_snapshot_probe.py`

## Optimization

Most Hugging Face snapshot sidecars discovered by the dataset registry follow a single-directory layout such as `config-00/train-00000.jsonl`. That common case does not need full path normalization, path-parts list materialization, or parent-part scanning. This slice adds a single-forward-slash fast path that:

1. confirms the relative path has exactly one `/` and no Windows separator,
2. derives the first directory and filename directly from string indexes,
3. preserves default-config directories via `_DEFAULT_CONFIG_FIRST_PARTS`, and
4. falls back to the existing normalized path-parts implementation for flat, multi-directory, empty, or Windows-style paths.

## Verification Plan

- Focused pytest for dataset registry behavior and PR-scoped performance selection.
- Changed-scope coverage via the registered probe coverage command.
- Local Linux registered probe run for `dataset-registry-snapshot-inference-single-pass`.
- GitHub Actions PR-scoped performance report remains the merge gate.

## Environment Boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime effect is claimed.
