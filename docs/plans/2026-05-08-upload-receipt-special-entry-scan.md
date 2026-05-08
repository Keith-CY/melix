# Upload Receipt Special Entry Scan Optimization

## Goal

Reduce redundant filesystem metadata checks while collecting published file lists for upload receipts.

## Linux constraint

This is a Python-only slice that can be verified on Linux with focused pytest, changed-scope coverage, and the existing `upload-receipt-published-files-scandir` PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/model_ops/upload_receipt_pipeline.py`
- `services/mlx-worker-python/tests/test_maintenance_service.py`
- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/upload_receipt_published_files_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Optimization

`_collect_published_file_list()` currently calls `DirEntry.is_dir(follow_symlinks=True)` for any entry that is neither a real directory nor a real file when symlinks are not followed. That extra follow-symlink directory check is only needed for symlink entries so directory symlinks can be excluded while file and broken symlinks remain published.

The optimized path checks `entry.is_symlink()` first and only performs the follow-symlink directory probe for symlinks. Non-symlink special entries can be published directly without the redundant follow check.

## Probe and success metric

Reuse registered probe `upload-receipt-published-files-scandir` and extend its workload with synthetic special entries. The strongest structural metric is `special_entry_follow_dir_checks_mean`: origin/main performs one follow-directory check per special entry per scan, while the optimized branch should drive that metric to `0.0` for non-symlink special entries while preserving the published file count.

## Verification commands

- Focused pytest for upload receipt published-file tests and PR-scoped probe tests.
- Coverage run for the same tests, followed by changed-scope coverage for touched executable Python files.
- `scripts/pr_scoped_performance_run.py --probe-id upload-receipt-published-files-scandir` against `origin/main` and head.
- `git diff --check`.
