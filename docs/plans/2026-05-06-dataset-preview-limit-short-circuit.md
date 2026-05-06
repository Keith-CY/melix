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

`read_hf_dataset_snapshot_rows(..., limit=N)` currently calls `_selected_dataset_files(...)`, which fully walks and materializes every supported dataset file before row reading begins. For no-split previews with a tiny limit, this makes preview latency and peak allocation scale with total file count even though only the first readable file is needed.

Add a lazy selected-file iterator for the no-split path so the reader can return as soon as the requested row limit is satisfied. Keep explicit split behavior unchanged because split filtering needs to know whether any matching split file exists.

## Performance probe

Register `dataset-registry-preview-limit-short-circuit` in the PR-scoped performance registry. The probe creates a synthetic snapshot with many JSONL files, reads `limit=1`, and reports:

- `elapsed_ms_mean`
- `peak_bytes_mean`
- `file_count`
- `rows_returned`

Success means the branch preserves row output while materially lowering elapsed time and peak traced allocation for a many-file `limit=1` preview.

## Verification commands

- Focused pytest for dataset registry and PR-scoped probe tests.
- Changed-scope coverage using `scripts/changed_scope_coverage.py`; require >=95% for touched executable lines.
- Local probe command from the registered `dataset-registry-preview-limit-short-circuit` probe.
- `git diff --check`.
