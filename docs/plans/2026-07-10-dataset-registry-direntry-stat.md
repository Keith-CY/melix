# Dataset registry DirEntry stat reuse

## Scope

This Python-only performance slice is limited to dataset registry snapshot file
materialization in `services/mlx-worker-python/worker/dataset_registry/catalog.py`.

`_dataset_files()` now uses a snapshot-scan helper that keeps the existing
sorted `os.scandir()` traversal and reads file sizes from the scan-time
`DirEntry.stat()` result. This avoids constructing a `Path` only to call
`Path.stat()` for every supported dataset file while preserving relative path,
file-format, split, config, and metadata behavior.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`dataset-registry-snapshot-inference-single-pass` in
`infra/perf/pr_scoped_probes.json`. The registry entry already includes focused
`test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/dataset_registry/catalog.py`
- `services/mlx-worker-python/tests/test_dataset_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_registry_snapshot_probe.py`

## Verification Plan

Run the registered focused tests, changed-scope coverage command, `git diff
--check`, and the registered `dataset-registry-snapshot-inference-single-pass`
probe locally on Linux before opening the PR. GitHub Actions PR-scoped
performance remains the merge gate for the registered probe report.
