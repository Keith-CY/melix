# Dataset registry file-format exact suffix fast path

## Scope

This Python-only performance slice is limited to `worker.dataset_registry.catalog._dataset_file_format()` while building dataset registry snapshot payloads. The behavior remains unchanged for metadata files, supported lowercase suffixes, supported uppercase suffixes, dotfiles, and trailing-dot names.

## Registered probe

The affected path is covered by the registered PR-scoped probe `dataset-registry-snapshot-inference-single-pass` in `infra/perf/pr_scoped_probes.json`.

The probe already includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/dataset_registry/catalog.py`
- `services/mlx-worker-python/tests/test_dataset_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_registry_snapshot_probe.py`

## Optimization

`_dataset_file_format()` previously lowercased every supported data-file suffix after locating the final dot. Dataset registry snapshots are dominated by lowercase files such as `*.jsonl`, so the slice first checks the exact suffix in `_SUPPORTED_DATASET_SUFFIXES` and only falls back to `suffix.lower()` for mixed-case or uppercase suffixes.

## Verification plan

1. Run the focused dataset registry test/probe command from the registered probe locally on Linux.
2. Run the changed-scope coverage command from the registered probe locally on Linux.
3. Run the registered PR-scoped performance probe locally against an `origin/main` baseline worktree and this branch.
4. Use the GitHub Actions PR-scoped performance report as the merge gate.

## Success criteria

- Focused tests pass.
- Changed-scope coverage remains at or above the repository threshold.
- The registered probe reports a lower or non-regressed `elapsed_ms_mean` for the optimized head.
