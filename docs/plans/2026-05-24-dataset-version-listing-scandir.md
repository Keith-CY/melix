# Dataset version listing scandir slice

This Python-only performance track keeps dataset-version listing behavior unchanged while reducing overhead in small, registered slices. The first slice replaced the one-level `Path.glob("*/dataset-version.json")` scan with an explicit `os.scandir()` pass. A follow-up changed shared JSON manifest loading from text decoding to byte loading. The current slice keeps the same registered listing probe and removes per-manifest `Path` construction from the listing hot path by carrying `os.scandir()` string paths into a direct binary JSON load.

## Scope

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_versioning.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_version_listing_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Registered probe

This track uses `dataset-version-listing-scandir` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries and runs on `ubuntu-latest`. The current string-path JSON loading follow-up is covered by the same registered probe because `list_dataset_versions(...)` discovers and reads every `dataset-version.json` manifest in the listing workload.

Metrics:

- `elapsed_ms_mean` / `elapsed_ms_p95`: lower is better for listing a synthetic dataset with many versions.
- `version_count`: informational workload size.

## Behavior

The listing still:

- returns only child directories that contain `dataset-version.json`;
- ignores files and empty directories under the versions root;
- returns an empty list when the versions root is absent or unreadable;
- sorts the final list by `(created_at, version_id)` exactly as before.

## Verification

Run the registered focused test command, changed-scope coverage command, and registered probe locally on Linux before opening the PR. GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.
