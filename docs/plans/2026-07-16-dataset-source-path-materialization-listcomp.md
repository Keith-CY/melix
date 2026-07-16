# Dataset Source Path Materialization List Comprehension

## Context

Dataset ingest source discovery walks large local input trees with `_iter_source_file_paths()` in `services/mlx-worker-python/worker/productization/dataset_preparation.py`. The PR-scoped probe `Dataset source records scandir` covers this path through `scripts/dataset_source_records_probe.py` and verifies source-file count, deterministic ordering, source-kind classification, and record byte accounting.

## Slice

Use a direct list comprehension when converting sorted filesystem path strings into `Path` instances. The traversal, symlink handling, sort order, and returned `Path` values stay unchanged; only the final materialization step changes from `list(map(Path, file_paths))` to a comprehension.

## Verification Plan

- Run the registered focused tests for `Dataset source records scandir`.
- Run changed-scope coverage for `dataset_preparation.py`, the ingest tests, PR-scoped registry tests, and the probe script.
- Run the registered probe locally on Linux and compare `elapsed_ms_mean` against the `origin/main` baseline.

## Results

Local Linux probe comparison on a synthetic tree with 250 directories, 28 files per directory, and 11 samples:

- `origin/main`: `elapsed_ms_mean=11.5307918114757`, `elapsed_ms_p95=12.23217905499041`
- candidate: `elapsed_ms_mean=11.482173100706529`, `elapsed_ms_p95=12.08088407292962`
- delta: `-0.04861871076917102 ms` mean (`~0.42%` faster), `-0.15129498206079006 ms` p95

This is a small Python-only hot-path improvement with unchanged behavior and local Linux validation.
