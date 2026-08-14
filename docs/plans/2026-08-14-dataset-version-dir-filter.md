# Dataset version directory-entry filter

This Python-only performance slice is limited to `worker.productization.dataset_preparation._iter_dataset_version_manifest_paths(...)`.

## Scope

The registered `dataset-version-listing-scandir` PR-scoped probe already covers dataset version listing through `services/mlx-worker-python/worker/productization/dataset_preparation.py`. This slice keeps the existing non-recursive `os.scandir()` traversal and version-listing semantics, but filters entries with `DirEntry.is_dir(follow_symlinks=False)` before building and opening `dataset-version.json` paths.

## Registered Probe

- Probe id: `dataset-version-listing-scandir`
- Watch path: `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- The probe fixture now includes one non-directory noise file per version directory so the optimization is measured against noisy dataset roots.

## Plan

1. Preserve normal version directory discovery and deterministic sort order.
2. Preserve fail-closed behavior for missing version roots and skip symlinked version directories.
3. Avoid exception-driven open attempts for top-level non-directory entries under `versions/`.
4. Run focused tests, changed-scope coverage, and the registered local Linux probe before opening the PR.

## Acceptance

Accept this slice only if focused behavior tests pass, changed-scope coverage remains at least 95%, and the registered local Linux probe shows an improvement for `elapsed_ms_mean`/`elapsed_ms_p95` on noisy version roots.