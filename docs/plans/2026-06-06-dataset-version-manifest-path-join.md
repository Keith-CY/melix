# Dataset Version Manifest Path Join Slice

## Scope

This Python-only performance slice is limited to dataset-version manifest path enumeration in `services/mlx-worker-python/worker/productization/dataset_preparation.py`.

## Registered Probe

The affected path is covered by registered PR-scoped probe `dataset-version-listing-scandir` in `infra/perf/pr_scoped_probes.json`. The registry entry already provides focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_versioning.py`
- `scripts/dataset_version_listing_probe.py`

## Optimization

Keep the existing `os.scandir()` directory walk and replace the per-entry `os.path.join(...)` helper dispatch with direct POSIX-style manifest path construction for the repository-supported Linux/macOS runners. Bind `os.path.isfile` once before the loop to avoid repeated module attribute lookup in the hot path.

The behavior remains the same for Melix-supported platforms: only real version directories containing `dataset-version.json` are yielded, non-directories and empty directories remain ignored, and missing roots still return an empty listing.

## Verification Plan

1. Run the registered focused pytest command for `dataset-version-listing-scandir`.
2. Run the registered changed-scope coverage command.
3. Run the registered local probe repeatedly on Linux and compare against the `origin/main` baseline collected before the change.
4. Use the PR-scoped performance workflow as the final CI merge gate.
