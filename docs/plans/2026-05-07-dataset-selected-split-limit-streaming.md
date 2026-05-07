# Dataset selected-split limited read streaming

## Goal

Avoid materializing every matching dataset file when `read_hf_dataset_snapshot_rows(...)` is called with both a selected split and a small `limit`.

## Linux-only constraint

This slice is Python-only under `services/mlx-worker-python`, so it can be verified locally on Linux with focused pytest, changed-scope coverage, and a synthetic performance probe.

## Touched files

- `services/mlx-worker-python/worker/dataset_registry/catalog.py`
- `services/mlx-worker-python/tests/test_dataset_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_registry_selected_split_limit_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Probe definition

Register `dataset-registry-selected-split-limit-streaming` in the PR-scoped performance registry. The probe builds a synthetic dataset snapshot with many split files, requests `split="validation", limit=1`, and reports elapsed time, peak traced allocation, returned rows, and a structural file-read count.

## Success metrics

- Behavior unchanged: selected split row reading preserves order and output shape.
- Limited selected-split reads stop after the first matching file once the limit is satisfied.
- Changed executable line coverage is at least 95%.
- Local and PR-scoped probes show lower elapsed time and/or lower peak allocation for the selected-split limited read path.

## Verification commands

- Focused pytest for dataset registry and PR-scoped performance probe tests.
- Changed-scope coverage with `scripts/changed_scope_coverage.py`.
- Local base-vs-head run of `scripts/pr_scoped_performance_run.py --probe-id dataset-registry-selected-split-limit-streaming` or a direct probe run with concrete metrics.
- `git diff --check`.
