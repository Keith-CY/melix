# Download directory-size single-stat slice

## Scope

This slice is limited to the Python worker managed Hugging Face import path that computes the size of a materialized snapshot directory before writing download/import manifests.

Touched paths:

- `services/mlx-worker-python/worker/model_ops/download_pipeline.py`
- `services/mlx-worker-python/tests/test_download_pipeline_unit.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Registered probe

The affected path is covered by the PR-scoped probe `download-pipeline-directory-size-single-stat` in `infra/perf/pr_scoped_probes.json`.

The probe includes:

- a focused `test_command` for `test_download_pipeline_unit.py` and registry selection checks;
- a `coverage_command` that records changed-scope coverage for the download pipeline and related tests;
- a `probe_command` that builds a synthetic managed snapshot with 180 directories and 7,200 files, then measures `DownloadPipeline._directory_size()` over five samples.

Metrics:

- `elapsed_ms_mean` (`lower_is_better`)
- `elapsed_ms_min` (`lower_is_better`)

## Implementation plan

1. Preserve the explicit `os.scandir()` stack and non-recursive traversal shape.
2. Use `DirEntry.is_dir(follow_symlinks=False)` as the directory fast path and `DirEntry.is_file(follow_symlinks=False)` before reading file size so Linux directory entries that can answer from `d_type` avoid unnecessary stat calls for non-file entries.
3. Keep directory symlinks and file symlinks out of the size calculation, matching the non-following traversal contract.
4. Bind the hot-loop stack and scandir helpers once per call so the synthetic directory-size probe measures less repeated attribute lookup while keeping the same traversal shape.
5. Validate with focused tests, changed-scope coverage, and the registered probe locally on Linux before pushing.

Deviation note: the earlier single-`stat()` branch was semantically correct, but local Linux probe runs showed the `is_file()` guard is faster for the registered synthetic workload because regular directory entries can be classified before their size stat is needed.

## Success criteria

- Focused tests pass.
- Changed-scope coverage remains at or above 95%.
- The registered probe reports a non-regressive or improved `elapsed_ms_mean` versus the pre-change baseline.
