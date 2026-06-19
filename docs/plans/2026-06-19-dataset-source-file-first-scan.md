# Dataset Source File-First Scan

## Scope

This Python-only performance slice targets `_iter_source_file_paths()` in `services/mlx-worker-python/worker/productization/dataset_preparation.py`.
The affected path is already covered by the registered PR-scoped probe `dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`, including focused `test_command`, `coverage_command`, and `probe_command` entries.

## Optimization

The synthetic and expected ingest workload is file-heavy under source directories. The scan loop now tests `DirEntry.is_file(follow_symlinks=False)` before `DirEntry.is_dir(follow_symlinks=False)`, avoiding the directory check on every regular file while preserving the same sorted returned path order and non-following symlink behavior.

## Verification

- Focused dataset ingest tests.
- Registered changed-scope coverage command for `dataset-source-records-scandir`.
- Registered local Linux probe command before and after the change.

## Boundary

This slice changes only Python code and is locally verifiable on Linux. No Swift runtime effect is claimed.
