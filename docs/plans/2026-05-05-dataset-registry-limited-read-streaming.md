# Dataset Registry Limited Read Streaming Plan

## Goal

Reduce redundant dataset snapshot file enumeration when callers request a small unfiltered row preview with `read_hf_dataset_snapshot_rows(..., limit=N)`.

## Linux-only constraint

This slice is Python-only under `services/mlx-worker-python` and can be validated on Linux with focused pytest, changed-scope coverage, and a synthetic performance probe.

## Touched files

- `services/mlx-worker-python/worker/dataset_registry/catalog.py`
- `services/mlx-worker-python/tests/test_dataset_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`
- `scripts/dataset_registry_limit_probe.py`

## Performance probe

Register `dataset-registry-limited-read-streaming` in PR-scoped performance CI. The probe builds a synthetic cached dataset snapshot with many supported data files, calls `read_hf_dataset_snapshot_rows(..., limit=5)`, and reports:

- `elapsed_ms_mean` (lower is better)
- `dataset_files_yielded_mean` (lower is better; structural proof that limited reads stop before enumerating the full snapshot)
- `peak_bytes_mean` (informational)

## Success metrics

- Focused dataset registry tests pass.
- Changed-scope coverage for touched executable Python/test/probe lines is at least 95%.
- Local probe shows limited reads yield only the files needed for the requested limit instead of all synthetic files.
- PR-scoped performance CI runs the registered probe before merge.
