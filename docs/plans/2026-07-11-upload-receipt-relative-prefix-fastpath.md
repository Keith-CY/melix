# Upload receipt relative-prefix fast path

This Python-only performance slice is limited to published-file discovery in
`worker.model_ops.upload_receipt_pipeline._collect_published_file_list(...)`.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`upload-receipt-published-files-scandir` in `infra/perf/pr_scoped_probes.json`.

The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/model_ops/upload_receipt_pipeline.py`
- `services/mlx-worker-python/tests/test_maintenance_service.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/upload_receipt_published_files_probe.py`

## Optimization

Published-file traversal already uses `os.scandir(...)`, but each directory
entry still checked whether the current relative directory was empty before
constructing the published path. This slice stores a relative prefix in the
explicit traversal stack: the root prefix is empty and child directory prefixes
already include the trailing slash. Each entry can then construct its relative
path with one string concatenation and no per-entry conditional branch.

The output remains sorted and uses the same slash-separated relative paths for
files, file symlinks, and special entries. Directory symlink exclusion behavior
is unchanged.

2026-07-26 follow-up slice: the same registered probe now covers a narrower
file-first branch optimization inside the `os.scandir(...)` traversal. The
synthetic publish tree is file-heavy, so the traversal now tests
`DirEntry.is_file(follow_symlinks=False)` before the directory branch. Directory
entries still enter the explicit stack, directory symlinks remain excluded,
file symlinks and special entries remain published, and sorted relative output
is unchanged while regular files avoid the previous extra no-follow directory
check.

## Verification plan

1. Extend focused upload receipt tests to assert nested published paths still use
   slash-separated relative names after prefix-based traversal.
2. Run the registered focused test command for
   `upload-receipt-published-files-scandir` locally on Linux.
3. Run the registered changed-scope coverage command locally on Linux.
4. Run the registered probe locally before and after the change.
5. Use GitHub Actions PR-scoped performance as the merge gate.

## Success criteria

- Focused tests pass.
- Changed-scope coverage for touched files remains at or above 95%.
- The registered local and CI probes show non-regression or improvement for
  `elapsed_ms_mean`, and `special_entry_follow_dir_checks_mean` stays at `0.0`.