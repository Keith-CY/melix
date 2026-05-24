# Dataset version listing scandir slice

This Python-only performance slice keeps dataset-version listing behavior unchanged while replacing the one-level `Path.glob("*/dataset-version.json")` scan with an explicit `os.scandir()` pass.

## Scope

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_versioning.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_version_listing_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Registered probe

This slice registers `dataset-version-listing-scandir` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries and runs on `ubuntu-latest`.

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
