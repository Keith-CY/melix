# Dataset preview limit short-circuit optimization

## Goal

Reduce redundant filesystem traversal and path materialization when local Hugging Face dataset previews request only a small number of rows without an explicit split.

## Linux-only constraint

This is a Python-only worker/catalog slice and can be verified on Linux with focused pytest, changed-scope coverage, and a synthetic local probe.

## Touched files

- `services/mlx-worker-python/worker/dataset_registry/catalog.py`
- `services/mlx-worker-python/tests/test_dataset_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_registry_preview_limit_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Proposed change

`read_hf_dataset_snapshot_rows(..., limit=N)` now avoids the eager split-selection tuple for no-split previews, but `limit=1` previews still enter the generic supported-file iterator. That iterator sorts every entry in the first data directory before yielding the first readable file, so preview latency and peak allocation still scale with total file count.

Add a `limit=1` no-split preview helper that finds the first readable dataset file in the same sorted depth-first order by scanning for the next minimum entry instead of sorting and materializing the full directory. Keep explicit split behavior unchanged because split filtering must know whether any matching split file exists before returning no rows.

## Performance probe

Register `dataset-registry-preview-limit-short-circuit` in the PR-scoped performance registry. The probe creates a synthetic snapshot with many JSONL files, reads `limit=1`, and reports:

- `elapsed_ms_mean`
- `peak_bytes_mean`
- `file_count`
- `rows_returned`

Success means the branch preserves row output while materially lowering elapsed time and peak traced allocation for a many-file `limit=1` preview.

## Follow-up: multi-row no-split limit return

A later Python-only slice keeps the same registered `dataset-registry-preview-limit-short-circuit` probe and tightens `read_hf_dataset_snapshot_rows(..., limit=N)` for no-split previews where `N > 1`. Once row materialization reaches the requested limit, the reader now returns immediately instead of advancing the supported-file iterator one additional path before observing `remaining == 0`. Explicit split behavior remains unchanged except for the same safe early return after enough rows have been collected.

The registered probe now also reports `multi_limit_elapsed_ms_mean` and `multi_limit_dataset_files_yielded_mean` so CI can validate the multi-row limit path in addition to the existing `limit=1` and zero-limit paths.

## Verification commands

- Focused pytest for dataset registry and PR-scoped probe tests.
- Changed-scope coverage using `scripts/changed_scope_coverage.py`; require >=95% for touched executable lines.
- Local probe command from the registered `dataset-registry-preview-limit-short-circuit` probe.
- `git diff --check`.
