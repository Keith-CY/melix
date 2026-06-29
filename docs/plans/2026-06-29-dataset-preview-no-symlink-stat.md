# Dataset preview no-symlink stat slice

## Scope

This Python-only performance slice is limited to the dataset registry preview
file scanner in `worker.dataset_registry.catalog`. The scanner is used by
`read_hf_dataset_snapshot_rows(..., limit=...)` when no explicit split is
requested.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`dataset-registry-preview-limit-short-circuit` in
`infra/perf/pr_scoped_probes.json`.

The probe already includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/dataset_registry/catalog.py`
- `services/mlx-worker-python/tests/test_dataset_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_registry_preview_limit_probe.py`

## Optimization hypothesis

The preview scanner only needs real directories and real supported dataset
files. Directory symlinks can trigger extra metadata work and recursive scans
outside the dataset snapshot. This slice changes the preview-only scan helpers
to call `DirEntry.is_dir(follow_symlinks=False)` and
`DirEntry.is_file(follow_symlinks=False)`.

Expected impact:

- Avoid symlink target stat/follow work while scanning preview candidates.
- Keep the sorted depth-first preview semantics for regular directories and
  files.
- Make directory symlink handling explicit and bounded for preview scans.

## Verification plan

1. Add regression coverage proving preview scans do not follow directory
   symlinks.
2. Run the registered focused test command locally on Linux.
3. Run the registered changed-scope coverage command locally on Linux.
4. Run the registered probe locally before and after the change and compare
   `elapsed_ms_mean`, `multi_limit_elapsed_ms_mean`, and peak memory metrics.
5. Use GitHub Actions PR-scoped performance as the merge gate before merging.

## Validation boundary

This is a Python/Linux-verifiable slice. No Swift runtime behavior is changed.
