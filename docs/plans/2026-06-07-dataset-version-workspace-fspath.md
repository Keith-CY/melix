# Dataset version listing workspace path fspath slice

This Python-only performance slice is limited to `list_dataset_versions(...)` in `services/mlx-worker-python/worker/productization/dataset_preparation.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe `dataset-version-listing-scandir` in `infra/perf/pr_scoped_probes.json`.

The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` values for:

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_versioning.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_version_listing_probe.py`

## Slice

`list_dataset_versions(...)` already streams version manifests with `os.scandir()`. This slice removes one per-call `Path(...)` construction for the returned `workspace_manifest_path` by using `os.fspath(...)`, and binds `time.perf_counter` locally so the final metrics timestamp avoids a second module attribute lookup.

Behavior remains unchanged for supported `str` and `Path` inputs: the listing preserves the caller-provided manifest path spelling and does not expand or resolve it.

## Verification plan

Run the registered focused tests, changed-scope coverage command, and local registered probe on Linux before opening the PR. Use the PR-scoped performance CI report as the merge gate.
