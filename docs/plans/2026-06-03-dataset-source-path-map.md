# Dataset source path materialization map slice

## Scope

This Python-only performance slice targets `worker.productization.dataset_preparation._iter_source_file_paths` after the scandir traversal has collected and sorted file path strings. The behavior remains unchanged: return a sorted `list[Path]` for regular files under the ingest source root while preserving the existing scandir error handling and symlink policy.

## Registered probe

The affected path is covered by the existing PR-scoped probe `dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The registered entry has focused `test_command`, `coverage_command`, and `probe_command` entries and watches:

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_source_records_probe.py`

## Implementation plan

1. Keep the scandir traversal, sorting, and filtering logic unchanged.
2. Replace the terminal list comprehension that materializes `Path` instances with `list(map(Path, file_paths))` to move the per-item call loop into the built-in map iterator.
3. Verify with the registered focused tests, changed-scope coverage, and the registered base-vs-head probe on Linux.

## Success criteria

- Focused dataset ingest and PR-scoped performance tests pass.
- Changed-scope coverage remains at 100% for the changed line.
- The registered probe reports lower `elapsed_ms_mean` on the head repository versus the base repository.
- PR-scoped performance CI selects and completes `dataset-source-records-scandir` successfully.
