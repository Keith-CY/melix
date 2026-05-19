# Dataset inferred split/config constant membership slice

## Scope

This Python-only performance slice is limited to dataset snapshot split/config inference in `services/mlx-worker-python/worker/dataset_registry/catalog.py`.

## Probe coverage

The affected path is covered by the registered PR-scoped performance probe `dataset-registry-snapshot-inference-single-pass` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for the dataset registry snapshot path and can run locally on Linux.

## Plan

1. Keep dataset discovery semantics unchanged for file names, nested config directories, and default/data split directories.
2. Avoid rebuilding small membership sets for every `_inferred_split_and_config(...)` call by hoisting them to module constants.
3. Add focused regression coverage for equivalent split/config inference on representative path shapes.
4. Verify with the registered focused tests, changed-scope coverage, and local registered probe before opening the PR.

## Success metrics

- Focused dataset registry tests pass.
- Changed-scope coverage for touched Python scope is at least 95%.
- `dataset_registry_snapshot_probe.py` reports lower mean elapsed time than the synced `origin/main` baseline, or the slice is rejected.
