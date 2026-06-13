# Dataset source records Path materialization map slice

This Python-only performance slice is limited to `worker.productization.dataset_preparation._iter_source_file_paths`.

## Scope

- Preserve the existing `os.scandir` directory walk, sorted path order, OSError handling, and `Path` return values.
- Change only the final string-to-`Path` materialization step from a Python list comprehension to `list(map(Path, ...))` so the registered dataset source records probe can measure whether the conversion loop is cheaper at the same file count.
- Keep the registered PR-scoped probe `dataset-source-records-scandir` as the validation source for tests, changed-scope coverage, and metrics.

## Validation

Run the focused dataset ingest tests, changed-scope coverage command, and `scripts/dataset_source_records_probe.py` locally on Linux before opening the PR. The same registered probe must pass in GitHub Actions before merge.
