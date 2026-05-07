# Dataset JSON Limited Read Streaming Optimization

## Goal

Reduce unnecessary work when previewing local Hugging Face dataset snapshots backed by top-level JSON array files with a small `limit`.

## Linux-only constraint

This slice only touches the Python worker dataset registry and is verifiable on Linux with focused pytest, changed-scope coverage, and a local PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/dataset_registry/catalog.py`
- `services/mlx-worker-python/tests/test_dataset_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_registry_split_match_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Optimization

`_read_rows_from_file(..., limit=N)` currently reads and decodes a full `.json` file before slicing rows. For top-level JSON arrays this means preview calls can parse every row even when the caller only needs the first row.

Add a limited top-level JSON-array reader that incrementally decodes array items until the requested number of dict rows is retained. Preserve existing full-parse fallback for mapping payloads, unbounded reads, and non-array JSON shapes.

## Probe

Update the existing `dataset-registry-limited-read-streaming` scoped probe to include a JSON limited-read workload that records:

- `json_limit_elapsed_ms_mean`
- `json_limit_peak_bytes_mean`
- `json_limit_read_text_calls_mean`
- `json_limit_rows_mean`

Success means identical limited rows, zero `Path.read_text()` calls on the limited top-level-array path, and lower peak allocation versus `origin/main`.

## Verification commands

- Focused pytest for dataset registry and probe script tests.
- Changed-scope coverage through `scripts/changed_scope_coverage.py` with >=95% coverage.
- Local base-vs-head run of `dataset-registry-limited-read-streaming` through `scripts/pr_scoped_performance_run.py`.
- `git diff --check`.
